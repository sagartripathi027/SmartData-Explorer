import os
import time
import uuid
import pandas as pd
from flask import Flask, request, render_template, session, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from analysis import analyze_data_structured, generate_heatmap
from ml_engine import train_ml_model, get_columns_info

app = Flask(__name__, template_folder="templates")
app.secret_key = os.urandom(24) # Required for session

# Limit file size (5MB)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# Upload and Model folders
UPLOAD_FOLDER = "uploads"
MODEL_FOLDER = "models"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MODEL_FOLDER, exist_ok=True)

def cleanup_old_files():
    """Cleanup uploaded CSVs/plots (1 hour) and ML models (24 hours)"""
    now = time.time()

    # Format: (directory, extensions, prefixes, max_age_seconds)
    cleanup_rules = [
        ("static", [".png"], ["heatmap_", "ml_plot_"], 3600),
        (UPLOAD_FOLDER, [".csv"], [""], 3600),
        (MODEL_FOLDER, [".pkl"], [""], 86400)
    ]

    for directory, exts, prefixes, max_age in cleanup_rules:
        abs_dir = os.path.abspath(directory)
        if os.path.exists(abs_dir):
            for f in os.listdir(abs_dir):
                if any(f.endswith(ext) for ext in exts):
                    if any(f.startswith(p) for p in prefixes):
                        fpath = os.path.abspath(os.path.join(abs_dir, f))

                        # Ensure the file is actually inside the target directory (path traversal check)
                        if fpath.startswith(abs_dir) and os.path.isfile(fpath):
                            if (now - os.path.getmtime(fpath)) > max_age:
                                try:
                                    os.remove(fpath)
                                except OSError as cleanup_err:
                                    # This also protects active downloads on Windows, as locked files will raise an OSError
                                    app.logger.warning(f"Failed to delete {fpath}: {cleanup_err}")

# ROUTES

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/documentation")
def documentation():
    return render_template("coming_soon.html", title="Documentation")

@app.route("/api")
def api():
    return render_template("coming_soon.html", title="API")

@app.route("/upload", methods=["POST"])
def upload():
    cleanup_old_files()

    if "file" not in request.files:
        return "<h3>No file uploaded.</h3>"

    file = request.files["file"]

    if file.filename == "":
        return "<h3>No file selected.</h3>"

    if not file.filename.endswith(".csv"):
        return "<h3>Please upload a CSV file only.</h3>"

    # Save with unique server-generated ID for security and ML reuse
    dataset_id = uuid.uuid4().hex
    filepath = os.path.join(UPLOAD_FOLDER, f"{dataset_id}.csv")
    file.save(filepath)

    # Associate dataset with this session
    session['dataset_id'] = dataset_id
    session['dataset_name'] = secure_filename(file.filename)

    try:
        # Read CSV
        df = pd.read_csv(filepath)

        # Run analysis
        results, cleaned_df = analyze_data_structured(df)

        # Generate HTML from DataFrames
        results['overview_html'] = results['overview_df'].to_html(classes="table", index=False)
        results['stats_html'] = results['stats_df'].to_html(classes="table", index=False) if not results['stats_df'].empty else "<p>No numeric columns.</p>"
        results['outliers_html'] = results['outliers_df'].to_html(classes="table", index=False) if not results['outliers_df'].empty else "<p>No numeric columns.</p>"

        heatmap = generate_heatmap(cleaned_df)
        preview = cleaned_df.head().to_html(classes="table", index=False)

        # Send to frontend
        return render_template(
            "result.html",
            preview=preview,
            results=results,
            heatmap=heatmap,
            dataset_name=session['dataset_name']
        )
    except Exception as e:
        app.logger.exception("Error processing uploaded dataset")
        if os.path.exists(filepath):
            os.remove(filepath)
        return "<h3>An error occurred processing the file. Please ensure it is a valid CSV.</h3>", 500
    # No longer deleting filepath in finally block to preserve for ML.
    # Handled by cleanup_old_files()

@app.route("/ml-config")
def ml_config():
    dataset_id = session.get('dataset_id')
    if not dataset_id:
        return redirect(url_for('home'))

    filepath = os.path.join(UPLOAD_FOLDER, f"{dataset_id}.csv")
    if not os.path.exists(filepath):
        return redirect(url_for('home'))

    columns_info = get_columns_info(filepath)
    return render_template("ml_config.html", columns=columns_info, dataset_name=session.get('dataset_name'))

@app.route("/train", methods=["POST"])
def train():
    dataset_id = session.get('dataset_id')
    if not dataset_id:
        return redirect(url_for('home'))

    filepath = os.path.join(UPLOAD_FOLDER, f"{dataset_id}.csv")
    if not os.path.exists(filepath):
        return "<h3>Dataset expired. Please upload again.</h3>", 400

    target_col = request.form.get("target_col")
    task_type = request.form.get("task_type")

    if not target_col or not task_type:
        return "<h3>Invalid ML configuration.</h3>", 400

    results = train_ml_model(filepath, target_col, task_type)

    if "error" in results:
        return render_template("ml_config.html", error=results["error"], columns=get_columns_info(filepath), dataset_name=session.get('dataset_name'))

    # Associate model with session for secure download
    session['model_id'] = results.get('model_id')

    return render_template("ml_result.html", results=results, dataset_name=session.get('dataset_name'))

@app.route("/download-model/<model_id>")
def download_model(model_id):
    if session.get('model_id') != model_id:
        return "<h3>Unauthorized or expired model download.</h3>", 403

    # Validate format to prevent directory traversal
    if not model_id.isalnum():
        return "<h3>Invalid model identifier.</h3>", 400

    model_path = os.path.join(MODEL_FOLDER, f"{model_id}.pkl")
    if not os.path.exists(model_path):
        return "<h3>Model file not found. It may have expired.</h3>", 404

    return send_file(model_path, as_attachment=True, download_name=f"model_{model_id}.pkl")

# RUN APP
if __name__ == "__main__":
    app.run(debug=True)