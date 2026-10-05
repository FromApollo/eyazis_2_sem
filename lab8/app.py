"""Flask web interface for laboratory work 8, variant 5."""

from flask import Flask, render_template


app = Flask(__name__)


@app.get("/")
def index():
    """Display the English literature text-to-speech interface."""
    return render_template("index.html", max_length=5000)


if __name__ == "__main__":
    app.run(port=5008, debug=True)
