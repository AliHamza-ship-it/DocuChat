import React, { useState } from 'react';
import api from '../api/client';
import { UploadCloud, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

export const DocumentUploader = ({ onUploadSuccess }) => {
    const [file, setFile] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [status, setStatus] = useState(null);

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
            setStatus(null);
        }
    };

    const handleUpload = async () => {
        if (!file) return;
        setUploading(true);
        setStatus(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await api.post('/docs/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setStatus({ type: 'success', text: `Indexed: ${res.data.chunks_processed} chunks created.` });
            setFile(null);
            if (onUploadSuccess) onUploadSuccess();
        } catch (err) {
            setStatus({ type: 'error', text: err.response?.data?.detail || 'Upload failed.' });
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="uploader-card">
            <h3 className="uploader-title">Upload Knowledge Base</h3>
            <p className="uploader-sub">Upload PDF or DOCX files for semantic retrieval.</p>

            <div className="dropzone">
                <input
                    type="file"
                    accept=".pdf,.docx"
                    onChange={handleFileChange}
                    id="file-input"
                    className="file-input"
                />
                <label htmlFor="file-input" className="file-label">
                    <UploadCloud size={32} className="upload-icon" />
                    <span>{file ? file.name : "Click or Drag PDF/DOCX here"}</span>
                </label>
            </div>

            {file && (
                <button
                    className="btn-primary btn-full mt-3"
                    onClick={handleUpload}
                    disabled={uploading}
                >
                    {uploading ? <><Loader2 className="animate-spin" size={18} /> Indexing Vector Embeddings...</> : "Upload & Parse Document"}
                </button>
            )}

            {status && (
                <div className={`status-banner ${status.type}`}>
                    {status.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                    <span>{status.text}</span>
                </div>
            )}
        </div>
    );
};