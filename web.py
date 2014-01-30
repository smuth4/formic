from flask import Flask
from flask import render_template
import ansibleengine
import ansible
import os

app = Flask(__name__)

base = "/home/kannibalox/ansible/"

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/playbook/")
def playbook():
    return render_template('playbook.html')

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
