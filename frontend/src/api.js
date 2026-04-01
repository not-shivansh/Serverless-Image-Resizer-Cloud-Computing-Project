const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

// ── Upload image via backend ────────────────────────────────
export async function uploadImage(file, onProgress) {
  const formData = new FormData();
  formData.append("file", file);

  // Use XMLHttpRequest for progress tracking
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/upload`);

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        const percent = Math.round((event.loaded / event.total) * 100);
        onProgress(percent);
      }
    });

    xhr.addEventListener("load", () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error(data.detail ?? "Upload failed."));
        }
      } catch {
        reject(new Error("Invalid response from server."));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Network error during upload.")));
    xhr.addEventListener("abort", () => reject(new Error("Upload aborted.")));

    xhr.send(formData);
  });
}

// ── Fetch image metadata ────────────────────────────────────
export async function fetchImage(imageId) {
  const response = await fetch(`${API_BASE_URL}/image/${imageId}`);
  return handleResponse(response);
}

// ── List recent images ──────────────────────────────────────
export async function listImages(limit = 20, offset = 0) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const response = await fetch(`${API_BASE_URL}/images?${params.toString()}`);
  return handleResponse(response);
}

// ── Delete image ────────────────────────────────────────────
export async function deleteImage(imageId) {
  const response = await fetch(`${API_BASE_URL}/image/${imageId}`, {
    method: "DELETE",
  });
  return handleResponse(response);
}

// ── Dynamic resize ──────────────────────────────────────────
export async function createDynamicResize({ imageId, width, height, format }) {
  const params = new URLSearchParams({
    image_id: imageId,
    width: String(width),
    height: String(height),
  });

  if (format) {
    params.set("format", format);
  }

  const response = await fetch(`${API_BASE_URL}/resize?${params.toString()}`);
  return handleResponse(response);
}

// ── Pre-signed URL (S3 mode) ────────────────────────────────
export async function getPresignedUrl(filename, contentType = "image/jpeg") {
  const params = new URLSearchParams({ filename, content_type: contentType });
  const response = await fetch(`${API_BASE_URL}/presign?${params.toString()}`);
  return handleResponse(response);
}

// ── Direct S3 upload with progress ──────────────────────────
export async function directS3Upload(presignedUrl, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", presignedUrl);
    xhr.setRequestHeader("Content-Type", file.type);

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        const percent = Math.round((event.loaded / event.total) * 100);
        onProgress(percent);
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error("S3 upload failed."));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Network error during S3 upload.")));
    xhr.send(file);
  });
}

// ── Confirm S3 upload ───────────────────────────────────────
export async function confirmUpload(body) {
  const response = await fetch(`${API_BASE_URL}/confirm-upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse(response);
}

// ── Health check ────────────────────────────────────────────
export async function healthCheck() {
  const response = await fetch(`${API_BASE_URL}/health`);
  return handleResponse(response);
}

// ── Response handler ────────────────────────────────────────
async function handleResponse(response) {
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail ?? "Request failed.");
  }

  return data;
}
