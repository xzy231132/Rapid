from flask import Flask, render_template, request, url_for

app = Flask(__name__)


@app.route('/')
def login():
    return render_template('login.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/resources')
def resources():
    return render_template('resources.html')

if __name__ == '__main__':
   app.run(debug = True)
