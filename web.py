import os
import ConfigParser
from flask import Flask
from flask import render_template, jsonify, request, redirect, url_for
import ansibleengine
import ansible
from ansible import callbacks

app = Flask(__name__)

@app.route("/")
@app.route("/inventories")
def index():
    return render_template('index.html', inventories=engine.listInventoryFiles())

@app.route("/hosts")
def hosts():
    return render_template('hosts.html', hosts=engine.listHosts(groups=True))

@app.route("/playbooks")
def playbooks():
    return render_template('playbooks.html', playbooks=engine.listPlaybooks())

@app.route("/playbooks/run")
def runPlaybook():
    return render_template('playbooks_run.html',
                           playbooks=engine.listPlaybooks(),
                           inventories=engine.listInventoryFiles(),
                           default_p=request.args.get('p', ''),
                           default_i=request.args.get('i', ''))

@app.route("/playbooks/launch", methods=['POST'])
def launchPlaybook():
    if request.method == "POST":
        engine.runPlaybook(request.form['inventory'], request.form['playbook'])
        return redirect(url_for('watchPlaybook'))
    return redirect(url_for('runPlaybook'))

@app.route("/playbooks/watch")
def watchPlaybook():
    return render_template('playbooks_watch.html')

@app.route("/playbooks/run/status")
def runningPlaybookStatus():
    return jsonify(engine.getPlaybookStatus())

def getConfig():
    global engine
    config_defaults = {
        "Bind": "127.0.0.1",
        "Base": os.path.dirname(os.path.realpath(__file__)),
        }
    config = ConfigParser.SafeConfigParser(config_defaults)
    config.read('formic.ini')
    
    base = config.get('Ansible', 'Base') 
    global bind
    bind = config.get('Web', 'Bind')
    
    engine = ansibleengine.AnsibleEngine(base)
    
if __name__ == "__main__":
    getConfig()
    app.run(host=bind, debug=True)
