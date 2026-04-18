from flask import Flask, render_template
import os

from auth import auth_bp, login_manager
from agents import agents_bp
from analytics import analytics_bp
from members import members_bp
from verify import verify_bp

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

login_manager.init_app(app)
login_manager.login_view = "auth.login"

app.register_blueprint(auth_bp)
app.register_blueprint(agents_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(members_bp)
app.register_blueprint(verify_bp)

@app.route("/")
def dashboard():
    return render_template("dashboard.html")

if __name__ == "__main__":
    app.run(debug=True)
