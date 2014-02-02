# A basic rewrite of the ansible-playbook command to make it more suitable to interface with the web ui
import os
import sys
import glob
from time import sleep
from threading import Thread
from multiprocessing import Queue, Lock
import Queue as Q
import ansible.playbook
from ansible import callbacks
from ansible import errors
from ansible import utils

class AnsibleEngine:
    def __init__(self, base):
        self.base = base
        self.status = "None"
        # An array of (msg, msg_status) tuples
        self.log = []
        self.playThread = None
        self.statusQueue = Queue()

    def basepath(self, filename):
        abspath = os.path.abspath(os.path.join(self.base, filename))
        if self.base in abspath:
            return abspath
        return None

    # List files in a pretty, minimal test format
    def listInventoryFiles(self):
        return [ os.path.basename(f.replace(self.base, '')) for f in self.__listInventoryFiles() ]
    
    # List absolute pathes
    def __listInventoryFiles(self):
        return glob.glob(os.path.join(self.base, "*.inv"))

    def listPlaybooks(self):
        return [ os.path.basename(f.replace(self.base, '')) for f in self.__listPlaybooks() ]

    def __listPlaybooks(self):
        return glob.glob(os.path.join(self.base, "*.yml"))

    # Returns a dictionary of hosts and relevant information
    def listHosts(self, groups=False):
        allHosts = {}
        for invFile in self.__listInventoryFiles():
            try:
                inv = ansible.inventory.Inventory(invFile)
            except errors.AnsibleError:
                allHosts = []
            hosts = inv.list_hosts()
            if len(hosts) == 0:
                continue
            for h in hosts:
                if groups:
                    allHosts[h] = [g.name for g in inv.groups_for_host(h) if g.name != "all"]
                else:
                    allHosts[h] = []
        return allHosts

    def runRaw(self, command):
        pass

    def getStatus(self):
        self.flushStatus()
        return {"status": self.status, "log": self.log}

    # Get all of the status updates out of the shared Queue
    def flushStatus(self):
        try:
            while True:
                # The queue should be filled with 3-element tuples, with a message, message status, and a global status, all of which might be None
                statusItem = self.statusQueue.get(False)
                if statusItem[0]:
                    self.log.append(statusItem[0:2])
                if statusItem[2]:
                    self.status = statusItem[2]
        except Q.Empty, e:
            # All items have been gotten
            pass

    def statusLog(self, msg=None, msg_status=None,status=None):
        self.statusQueue.put((msg, msg_status, status))

    # Begin the thread which will run the play book
    def runPlaybook(self, inventory, playbook):
        if self.playThread and self.playThread.is_alive():
            return False
        self.flushStatus()
        self.status = "None"
        self.log = []
        self.playThread = Thread(target=self.__runPlaybook, args=(inventory, playbook))
        self.playThread.start()
        return True

    # Internal command that does all the threaded lifting
    def __runPlaybook(self, inventory, playbook):
        self.statusLog(status="Initializing")
        inv = ansible.inventory.Inventory(os.path.join(self.base, inventory))
        inv.set_playbook_basedir(self.base)
        stats = callbacks.AggregateStats()
        playbook_cb = EnginePlaybookCallbacks(self.statusQueue, verbose=utils.VERBOSITY)
        runner_cb = EngineRunnerCallbacks(self.statusQueue)
        pb = ansible.playbook.PlayBook(
            playbook=os.path.join(self.base, playbook),
            inventory=inv,
            stats=stats,
            callbacks=playbook_cb,
            runner_callbacks=runner_cb,
            )
        self.statusLog("Ansible base is %s" % self.base)
        self.statusLog("Using inventory %s" % os.path.join(self.base, inventory), "info")
        self.statusLog("Using playbook %s" % os.path.join(self.base, playbook), "info")
        try:
            self.statusLog(status="Beginning run")
            pb.run()
            self.flushStatus()
            self.statusLog("Finished execution", status="Finished")
        except errors.AnsibleError, e:
            self.statusLog("Unknown ansible error occured", status="Finished - Error")
        # Clear host cache
        for host in self.listHosts():
            try:
                del pb.SETUP_CACHE[host]
            except KeyError:
                pass
        pb = None

# Overrides ansible's callbacks
# If more than one host will be tasked, this class will be executed in multiple processes
# This could be done as a module in the callbacks folder
class EngineRunnerCallbacks(callbacks.DefaultRunnerCallbacks):
    def __init__(self, statusQueue):
        self.statusQueue = statusQueue
        super(EngineRunnerCallbacks, self).__init__()

    def log(self, msg=None, msg_status=None, status=None):
        self.statusQueue.put((msg, msg_status, status))

    def on_ok(self, host, res):
        if res.get('changed', False):
            self.log("Changed - %s" % host, "success")
        else:
            self.log("OK - %s" % host, "success")
        super(EngineRunnerCallbacks, self).on_ok(host, res)

    def on_error(self, host, res):
        self.log("Error - %s" % host, "danger")
        super(EngineRunnerCallbacks, self).on_error(host, res)

    def on_failed(self, host, res):
        self.log("Failed - %s" % host, "danger")
        super(EngineRunnerCallbacks, self).on_failed(host, res)

    def on_no_hosts(self):
        self.log("No hosts!", "warning")
        super(EngineRunnerCallbacks, self).on_no_hosts()

    def on_skipped(self, host, item=None):
        msg = ''
        if item:
            msg = "Skipping: %s => (item=%s)" % (host, item)
        else:
            msg = "Skipping: %s" % host
        self.log(msg, "info")
        super(EngineRunnerCallbacks, self).on_skipped(host, item)


    
class EnginePlaybookCallbacks(callbacks.PlaybookCallbacks):
    def __init__(self, statusQueue, verbose=False):
        self.statusQueue = statusQueue
        self.verbose = verbose

    def log(self, msg=None, msg_status=None, status=None):
        self.statusQueue.put((msg, msg_status, status))

    def on_start(self):
        self.log(status="Starting")
        callbacks.call_callback_module('playbook_on_start')

    def on_notify(self, host, handler):
        self.log("Notifying handler '%s' of change" % handler)
        callbacks.call_callback_module('playbook_on_notify', host, handler)

    def on_no_hosts_matched(self):
        self.log("No hosts matched", "danger")
        callbacks.call_callback_module('playbook_on_no_hosts_matched')

    def on_no_hosts_remaining(self):
        self.log("No hosts remaining", "danger")
        callbacks.call_callback_module('playbook_on_no_hosts_remaining')

    def on_task_start(self, name, is_conditional):
        if is_conditional:
            self.log("Notification for '%s' started" % name, status="Running")
        else:
            self.log("Task '%s' started" % name, status="Running")
        callbacks.call_callback_module('playbook_on_task_start', name, is_conditional)

    def on_vars_prompt(self, varname, private=True, prompt=None, encrypt=None, confirm=False, salt_size=None, salt=None, default=None):
        self.log("Attempting to prompt for variable - behavior is undefined", msg_status="danger")

        # if result is false and default is not None
        if not result and default:
            result = default


        if encrypt:
            result = utils.do_encrypt(result,encrypt,salt_size,salt)

        callbacks.call_callback_module( 'playbook_on_vars_prompt', varname, private=private, prompt=prompt,
                               encrypt=encrypt, confirm=confirm, salt_size=salt_size, salt=None, default=default
                            )

        return result

    def on_setup(self):
        self.log("Gather host facts", status="Gathering facts")
        callbacks.call_callback_module('playbook_on_setup')

    def on_import_for_host(self, host, imported_file):
        self.log("Host %s is importing $s" % (host, imported_file), status="Gathering facts")
        callbacks.call_callback_module('playbook_on_import_for_host', host, imported_file)

    def on_not_import_for_host(self, host, missing_file):
        self.log("Host %s is not importing $s" % (host, imported_file), status="Gathering facts")
        callbacks.call_callback_module('playbook_on_not_import_for_host', host, missing_file)

    def on_play_start(self, pattern):
        self.log("Play '%s' started" % pattern)
        callbacks.call_callback_module('playbook_on_play_start', pattern)

    def on_stats(self, stats):
        callbacks.call_callback_module('playbook_on_stats', stats)
    

if __name__ == "__main__":
    e = AnsibleEngine()
    print e.listHosts(True)
    print e.runPlaybook("inventory.inv", "common.yml")
    print e.getPlaybookStatus()
    sleep(5)
    print e.getPlaybookStatus()
    
