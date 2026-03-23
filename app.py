import config
from flask import Flask

from routes import register_blueprints

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

register_blueprints(app)

# =====================================================
# RUN
# =====================================================
if __name__ == '__main__':
    print("AI Paralegal Assistant (Multi-Agent) is running...")
    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
