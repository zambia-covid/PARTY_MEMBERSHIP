from flask import Flask
from auth import auth_bp, login_manager
from members import members_bp
from analytics import analytics_bp

app = Flask(__name__)
app.secret_key = "supersecret"

login_manager.init_app(app)

app.register_blueprint(auth_bp)
app.register_blueprint(members_bp)
app.register_blueprint(analytics_bp)

@app.route("/")
def home():
    return "System Running"

if __name__ == "__main__":
    app.run(debug=True)
