import os
from flask import Flask, request, render_template
import pandas as pd
import time
from analysis import analyze_data, generate_heatmap
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder="templates")

# Limit file size (5MB)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# Upload folder
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ROUTES

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    # Lazy cleanup of old heatmaps (> 300 seconds)
    try:
        static_dir = os.path.join(app.root_path, "static")
        if os.path.exists(static_dir):
            now = time.time()
            for f in os.listdir(static_dir):
                if f.startswith("heatmap_") and f.endswith(".png"):
                    fpath = os.path.join(static_dir, f)
                    if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > 300:
                        try:
                            os.remove(fpath)
                        except Exception as cleanup_err:
                            app.logger.warning(f"Failed to delete {fpath}: {cleanup_err}")
    except Exception as e:
        app.logger.warning(f"Cleanup error: {e}")

    if "file" not in request.files:
        return "<h3>No file uploaded.</h3>"

    file = request.files["file"]

    if file.filename == "":
        return "<h3>No file selected.</h3>"

    if not file.filename.endswith(".csv"):
        return "<h3>Please upload a CSV file only.</h3>"

    # Secure filename
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        # Read CSV
        df = pd.read_csv(filepath)

        # Run analysis
        result = analyze_data(df)

        # Generate heatmap ✅ (THIS WAS MISSING)
        heatmap = generate_heatmap(df)

        # Preview
        preview = df.head().to_html(classes="table", index=False)

        # Send to frontend
        return render_template(
            "result.html",
            preview=preview,
            result=result,
            heatmap=heatmap
        )

    except Exception as e:
        app.logger.exception("Error processing uploaded dataset")
        return "<h3>An error occurred processing the file. Please ensure it is a valid CSV.</h3>", 500

    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


# RUN APP
if __name__ == "__main__":
    app.run(debug=True)