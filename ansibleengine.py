# A basic rewrite of the ansible-playbook command to make it more suitable to interface with the web ui
import os
import sys
import glob
from time import sleep
from threading import Thread
import ansible.playbook
from ansible import callbacks
from ansible import errors
from ansible import utils

class AnsibleEngine:
    def __init__(self, base):
        self.base = base
        self.playbookStatus = {"status": "None", "log": [], "stats": {}}
        self.playThread = None

    def listInventoryFiles(self):
        return glob.glob(self.base + "*.inv")
       
    def runRaw(self, command):
        pass

    def getPlaybookStatus(self):
        return self.playbookStatus

    def runPlaybook(self, inventory, playbook):
        if self.playThread and self.playThread.is_alive():
            return "thread in progress"
        self.playbookStatus = {"status": "None", "log": [], "stats": {}}
        self.playThread = Thread(target=self.__runPlaybook, args=(inventory, playbook))
        self.playThread.start()

    # internal command that does all the threaded lifting
    def __runPlaybook(self, inventory, playbook):
        t = []
        inv = ansible.inventory.Inventory(inventory)
        inv.set_playbook_basedir(self.base)
        stats = callbacks.AggregateStats()
        playbook_cb = EnginePlaybookCallbacks(self.playbookStatus, verbose=utils.VERBOSITY)
        runner_cb = EngineRunnerCallbacks()
        pb = ansible.playbook.PlayBook(
            playbook=playbook,
            inventory=inv,
            stats=stats,
            callbacks=playbook_cb,
            runner_callbacks=runner_cb,
            )
        playnum = 0
        for (play_ds, play_basedir) in zip(pb.playbook, pb.play_basedirs):
            playnum += 1
            play = ansible.playbook.Play(pb, play_ds, play_basedir)
            label = play.name
            for task in play.tasks():
                if getattr(task, 'name', None) is not None:
                    t += [task.name]
        try:
            pb.run()
            self.playbookStatus['status'] = "Stopped"
            print str(pb.stats)
        except errors.AnsibleError, e:
            print "Ansible error"
        # Clear cache
        for host in self.listHosts():
            try:
                del pb.SETUP_CACHE[host]
            except KeyError:
                pass
        pb = None
        return t

    def listHosts(self, groups=False):
        allHosts = {}
        for invFile in self.listInventoryFiles():
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

    def listPlaybooks(self):
        return glob.glob(self.base + "*.yml")

class EngineRunnerCallbacks(callbacks.DefaultRunnerCallbacks):
    def __init__(self):
        super(EngineRunnerCallbacks, self).__init__()

class EnginePlaybookCallbacks(callbacks.PlaybookCallbacks):
    def __init__(self, statusDict, verbose=False):
        self.status = statusDict
        self.verbose = verbose

    def on_start(self):
        self.status['status'] = "Started"
        super(EnginePlaybookCallbacks, self).on_start()

    def on_notify(self, host, handler):
        self.status['log'] += ["Notifying handler '%s' of change" % handler]
        super(EnginePlaybookCallbacks, self).on_notify(host, handler)

    def on_no_hosts_matched(self):
        callbacks.display("skipping: no hosts matched", color='cyan')
        callbacks.call_callback_module('playbook_on_no_hosts_matched')

    def on_no_hosts_remaining(self):
        callbacks.display("\nFATAL: all hosts have already failed -- aborting", color='red')
        callbacks.call_callback_module('playbook_on_no_hosts_remaining')

    def on_task_start(self, name, is_conditional):
        self.status['log'] += ["Task '%s' started" % name]
        self.status['status'] = "Running"
        msg = "TASK: [%s]" % name
        if is_conditional:
            msg = "NOTIFIED: [%s]" % name

        callbacks.call_callback_module('playbook_on_task_start', name, is_conditional)

    def on_vars_prompt(self, varname, private=True, prompt=None, encrypt=None, confirm=False, salt_size=None, salt=None, default=None):

        if prompt and default:
            msg = "%s [%s]: " % (prompt, default)
        elif prompt:
            msg = "%s: " % prompt
        else:
            msg = 'input for %s: ' % varname

        def prompt(prompt, private):
            if private:
                return getpass.getpass(prompt)
            return raw_input(prompt)


        if confirm:
            while True:
                result = prompt(msg, private)
                second = prompt("confirm " + msg, private)
                if result == second:
                    break
                display("***** VALUES ENTERED DO NOT MATCH ****")
        else:
            result = prompt(msg, private)

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
        self.status['log'].append("Gather facts on hosts")
        self.status['status'] = "Gathering facts"
        callbacks.display(callbacks.banner("GATHERING FACTS"))
        callbacks.call_callback_module('playbook_on_setup')

    def on_import_for_host(self, host, imported_file):
        msg = "%s: importing %s" % (host, imported_file)
        callbacks.display(msg, color='cyan')
        callbacks.call_callback_module('playbook_on_import_for_host', host, imported_file)

    def on_not_import_for_host(self, host, missing_file):
        msg = "%s: not importing file: %s" % (host, missing_file)
        callbacks.display(msg, color='cyan')
        callbacks.call_callback_module('playbook_on_not_import_for_host', host, missing_file)

    def on_play_start(self, pattern):
        self.status['log'] += ["Play '%s' started" % pattern]
        callbacks.display(callbacks.banner("PLAY [%s]" % pattern))
        callbacks.call_callback_module('playbook_on_play_start', pattern)

    def on_stats(self, stats):
        self.status['status'] = "Computing stats"
        callbacks.call_callback_module('playbook_on_stats', stats)
        self.status['status'] = "Stopped"
    

if __name__ == "__main__":
    e = AnsibleEngine("/home/kannibalox/ansible/")
    print e.listHosts(True)
    print e.runPlaybook("/home/kannibalox/ansible/inventory.inv", "/home/kannibalox/ansible/nginx.yml")
    print e.getPlaybookStatus()
    sleep(5)
    print e.getPlaybookStatus()
    
