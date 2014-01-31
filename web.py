from flask import Flask
from flask import render_template, jsonify, request, redirect, url_for
import ansibleengine
import ansible
from ansible import callbacks
import os

app = Flask(__name__)

base = "/home/kannibalox/ansible/"
engine = ansibleengine.AnsibleEngine(base)

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

@app.route("/playbooks/run", methods=['POST', 'GET'])
def runPlaybook():
    if request.method == "POST":
        engine.runPlaybook(request.form['inventory'], request.form['playbook'])
        return redirect(url_for('watchPlaybook'))
    return render_template('playbooks_run.html', playbooks=engine.listPlaybooks(), inventories=engine.listInventoryFiles())

@app.route("/playbooks/watch")
def watchPlaybook():
    return render_template('playbooks_watch.html')

@app.route("/playbooks/run/status")
def runningPlaybookStatus():
    return jsonify(engine.getPlaybookStatus())
    
if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
