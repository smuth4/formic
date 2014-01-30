# A basic rewrite of the ansible-playbook command to make it more suitable to interface with the web ui
import os
import sys
import ansible.playbook

class AnsibleEngine:
    def __init__(self, base):
       self.base = base
       
    def runRaw(self, command):
        pass

    def listHosts(self):
        pass

    def listTasks(self):
        pass
