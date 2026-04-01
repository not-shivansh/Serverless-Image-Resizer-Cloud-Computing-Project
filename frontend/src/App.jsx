import { useCallback, useEffect, useState } from "react";

import { createDynamicResize, deleteImage, fetchImage, listImages, uploadImage } from "./api";

const formats = ["jpg", "png", "webp"];

function formatBytes(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [imageRecord, setImageRecord] = useState(null);
  const [customVariant, setCustomVariant] = useState(null);
  const [lookupId, setLookupId] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [history, setHistory] = useState([]);
  const [toast, setToast] = useState(null);
  const [resizeForm, setResizeForm] = useState({
    width: 400,
    height: 400,
    format: "webp",
  });
  const [status, setStatus] = useState({
    type: "idle",
    message: "Drop an image or click to upload — get instant resized variants.",
  });

  // ── Load history on mount ─────────────────────────────────
  const loadHistory = useCallback(async () => {
    try {
      const data = await listImages(12, 0);
      setHistory(data.images || []);
    } catch {
      // silently fail — history is optional
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // ── Toast helper ──────────────────────────────────────────
  function showToast(msg) {
    setToast(msg);
    setTimeout(() => setToast(null), 2600);
  }

  // ── Copy to clipboard ────────────────────────────────────
  async function copyUrl(url) {
    try {
      await navigator.clipboard.writeText(url);
      showToast("✓ URL copied to clipboard");
    } catch {
      showToast("Could not copy URL");
    }
  }

  // ── File selection (input or drop) ────────────────────────
  function handleFileSelect(file) {
    if (file) {
      setSelectedFile(file);
      setUploadProgress(0);
    }
  }

  // ── Drag & Drop ───────────────────────────────────────────
  function handleDragOver(e) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    handleFileSelect(file);
  }

  // ── Upload ────────────────────────────────────────────────
  async function handleUpload(event) {
    event.preventDefault();
    if (!selectedFile) {
      setStatus({ type: "error", message: "Choose an image file first." });
      return;
    }

    try {
      setStatus({ type: "loading", message: "Uploading and processing image..." });
      setUploadProgress(0);

      const response = await uploadImage(selectedFile, (progress) => {
        setUploadProgress(progress);
      });

      setImageRecord(response.image);
      setCustomVariant(null);
      setLookupId(response.image.image_id);
      setUploadProgress(100);

      const time = response.image.processing_time_ms
        ? ` in ${response.image.processing_time_ms.toFixed(0)}ms`
        : "";
      setStatus({
        type: "success",
        message: `${response.message}${time} — ${response.image.variants.length} variants created.`,
      });

      showToast("✨ Image processed successfully");
      loadHistory();
    } catch (error) {
      setStatus({ type: "error", message: error.message });
      setUploadProgress(0);
    }
  }

  // ── Fetch by ID ───────────────────────────────────────────
  async function handleLookup(event) {
    event.preventDefault();
    if (!lookupId.trim()) {
      setStatus({ type: "error", message: "Enter an image ID to fetch." });
      return;
    }

    try {
      setStatus({ type: "loading", message: "Loading image metadata..." });
      const response = await fetchImage(lookupId.trim());
      setImageRecord(response.image);
      setCustomVariant(null);
      setStatus({ type: "success", message: response.message });
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    }
  }

  // ── Dynamic resize ───────────────────────────────────────
  async function handleDynamicResize(event) {
    event.preventDefault();
    if (!imageRecord) {
      setStatus({ type: "error", message: "Upload or fetch an image before resizing." });
      return;
    }

    try {
      setStatus({ type: "loading", message: "Generating custom variant..." });
      const response = await createDynamicResize({
        imageId: imageRecord.image_id,
        ...resizeForm,
      });
      setCustomVariant(response.variant);
      setStatus({
        type: "success",
        message: `Created ${response.variant.label} in ${response.variant.format.toUpperCase()} (${response.variant.width}×${response.variant.height}).`,
      });
      showToast("🎨 Custom variant created");
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    }
  }

  // ── Load from history ─────────────────────────────────────
  function handleHistoryClick(record) {
    setImageRecord(record);
    setCustomVariant(null);
    setLookupId(record.image_id);
    setStatus({ type: "success", message: `Loaded ${record.original_filename}` });
  }

  // ── Delete image ──────────────────────────────────────────
  async function handleDelete(e, imageId) {
    e.stopPropagation(); // prevent triggering history click
    if (!confirm("Delete this image and all its variants?")) return;

    try {
      setStatus({ type: "loading", message: "Deleting image..." });
      await deleteImage(imageId);
      // Clear active image if it's the one being deleted
      if (imageRecord?.image_id === imageId) {
        setImageRecord(null);
        setCustomVariant(null);
        setLookupId("");
      }
      showToast("🗑️ Image deleted");
      setStatus({ type: "success", message: "Image deleted successfully." });
      loadHistory();
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    }
  }

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="app-shell">
      {/* HERO */}
      <section className="hero-card">
        <div className="hero-top">
          <span className="hero-badge">
            <span className="dot" />
            Cloud Computing Project
          </span>
        </div>
        <h1>Serverless Image Resizer</h1>
        <p className="hero-copy">
          Upload images and instantly generate optimized thumbnail, medium, and large variants.
          Powered by AWS S3, Lambda, API Gateway &amp; CloudFront — with local development support.
        </p>

        <div className="hero-stats">
          <div className="hero-stat">
            <span className="value">3</span>
            <span className="label">Preset Sizes</span>
          </div>
          <div className="hero-stat">
            <span className="value">JPG · PNG · WebP</span>
            <span className="label">Format Support</span>
          </div>
          <div className="hero-stat">
            <span className="value">&lt; 2s</span>
            <span className="label">Processing Time</span>
          </div>
          <div className="hero-stat">
            <span className="value">5 MB</span>
            <span className="label">Max File Size</span>
          </div>
        </div>

        <div className={`status-banner ${status.type}`}>{status.message}</div>
      </section>

      {/* WORKSPACE */}
      <main className="workspace-grid">
        {/* Upload Panel */}
        <section className="panel">
          <h2><span className="icon">📤</span> Upload</h2>
          <form onSubmit={handleUpload} className="stack">
            <div
              className={`dropzone ${isDragging ? "dragging" : ""}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <span className="drop-icon">🖼️</span>
              <p className="drop-text">
                <strong>Drop image here</strong> or click to browse
              </p>
              <p className="drop-hint">JPG, PNG, WebP — up to 5 MB</p>
              <input
                type="file"
                accept=".jpg,.jpeg,.png,.webp"
                onChange={(e) => handleFileSelect(e.target.files?.[0])}
              />
            </div>

            {selectedFile && (
              <div className="file-preview">
                <span className="file-icon">📎</span>
                <div className="file-info">
                  <div className="file-name">{selectedFile.name}</div>
                  <div className="file-size">{formatBytes(selectedFile.size)}</div>
                </div>
              </div>
            )}

            {uploadProgress > 0 && uploadProgress < 100 && (
              <div className="progress-bar-container">
                <div className="progress-bar" style={{ width: `${uploadProgress}%` }} />
              </div>
            )}

            <button type="submit" disabled={!selectedFile || status.type === "loading"}>
              {status.type === "loading" ? "Processing..." : "Upload & Generate Variants"}
            </button>
          </form>
        </section>

        {/* Fetch Panel */}
        <section className="panel">
          <h2><span className="icon">🔍</span> Fetch Image</h2>
          <form onSubmit={handleLookup} className="stack">
            <label className="field">
              <span>Image ID</span>
              <input
                type="text"
                value={lookupId}
                placeholder="Paste an image_id..."
                onChange={(e) => setLookupId(e.target.value)}
              />
            </label>
            <button type="submit" className="secondary">
              Fetch metadata
            </button>
          </form>

          {/* Mini History */}
          {history.length > 0 && (
            <>
              <h2 style={{ marginTop: "1.5rem" }}><span className="icon">🕐</span> Recent</h2>
              <div className="history-grid">
                {history.slice(0, 6).map((record) => (
                  <div
                    key={record.image_id}
                    className="history-item"
                    onClick={() => handleHistoryClick(record)}
                  >
                    <img src={record.variants?.[0]?.url || ""} alt={record.original_filename} />
                    <div className="history-name">{record.original_filename}</div>
                    <div className="history-date">{formatDate(record.created_at)}</div>
                    <button
                      type="button"
                      className="delete-btn"
                      title="Delete image"
                      onClick={(e) => handleDelete(e, record.image_id)}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

        {/* Dynamic Resize Panel */}
        <section className="panel panel-wide">
          <h2><span className="icon">✂️</span> Dynamic Resize</h2>
          <form onSubmit={handleDynamicResize} className="resize-grid">
            <label className="field">
              <span>Width</span>
              <input
                type="number"
                min="1"
                max="4000"
                value={resizeForm.width}
                onChange={(e) =>
                  setResizeForm((cur) => ({ ...cur, width: Number(e.target.value) }))
                }
              />
            </label>
            <label className="field">
              <span>Height</span>
              <input
                type="number"
                min="1"
                max="4000"
                value={resizeForm.height}
                onChange={(e) =>
                  setResizeForm((cur) => ({ ...cur, height: Number(e.target.value) }))
                }
              />
            </label>
            <label className="field">
              <span>Format</span>
              <select
                value={resizeForm.format}
                onChange={(e) =>
                  setResizeForm((cur) => ({ ...cur, format: e.target.value }))
                }
              >
                {formats.map((f) => (
                  <option key={f} value={f}>
                    {f.toUpperCase()}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" disabled={!imageRecord || status.type === "loading"}>
              Create variant
            </button>
          </form>
        </section>

        {/* Output Panel */}
        <section className="panel panel-wide">
          <div className="panel-header">
            <div>
              <h2><span className="icon">🎯</span> Output</h2>
              <p className="subtle">
                Preset and custom optimized variants.
              </p>
            </div>
            {imageRecord && (
              <code onClick={() => copyUrl(imageRecord.image_id)} title="Click to copy ID">
                {imageRecord.image_id.slice(0, 12)}…
              </code>
            )}
          </div>

          {imageRecord ? (
            <div className="results-stack">
              {/* Preset Variants */}
              <div className="variant-grid">
                {imageRecord.variants.map((variant) => (
                  <article key={variant.label} className="variant-card">
                    <div className="variant-meta">
                      <strong>{variant.label}</strong>
                      <span>
                        {variant.width} × {variant.height} · {variant.format.toUpperCase()}
                        {variant.size_bytes > 0 && (
                          <> · {formatBytes(variant.size_bytes)}</>
                        )}
                      </span>
                    </div>
                    <img src={variant.url} alt={variant.label} />
                    <div className="variant-actions">
                      <a href={variant.url} target="_blank" rel="noreferrer">
                        ↗ Open
                      </a>
                      <button
                        type="button"
                        className="copy-btn"
                        onClick={() => copyUrl(variant.url)}
                      >
                        📋 Copy
                      </button>
                    </div>
                  </article>
                ))}

                {/* Custom Variant */}
                {customVariant && (
                  <article className="variant-card custom">
                    <div className="variant-meta">
                      <strong>{customVariant.label}</strong>
                      <span>
                        {customVariant.width} × {customVariant.height} · {customVariant.format.toUpperCase()}
                        {customVariant.size_bytes > 0 && (
                          <> · {formatBytes(customVariant.size_bytes)}</>
                        )}
                      </span>
                    </div>
                    <img src={customVariant.url} alt={customVariant.label} />
                    <div className="variant-actions">
                      <a href={customVariant.url} target="_blank" rel="noreferrer">
                        ↗ Open
                      </a>
                      <button
                        type="button"
                        className="copy-btn"
                        onClick={() => copyUrl(customVariant.url)}
                      >
                        📋 Copy
                      </button>
                    </div>
                  </article>
                )}
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <span className="empty-icon">📷</span>
              <p>No image loaded yet.</p>
              <p>Upload a new file or fetch an existing record by image ID.</p>
            </div>
          )}
        </section>
      </main>

      {/* Toast */}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
