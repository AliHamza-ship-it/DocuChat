import React, { useEffect, useState } from 'react';
import { DocumentUploader } from './DocumentUploader';
import api from '../api/client';
import { FileText, Database } from 'lucide-react';

export const Sidebar = ({ refreshTrigger, onUploadSuccess }) => {
    const [documents, setDocuments] = useState([]);

    const fetchDocuments = async () => {
        try {
            const res = await api.get('/docs/list');
            setDocuments(res.data);
        } catch (err) {
            console.error('Failed to fetch document library', err);
        }
    };

    useEffect(() => {
        fetchDocuments();
    }, [refreshTrigger]);

    return (
        <aside className="sidebar">
            <DocumentUploader onUploadSuccess={() => {
                fetchDocuments();
                if (onUploadSuccess) onUploadSuccess();
            }} />

            <div className="doc-library">
                <div className="doc-library-header">
                    <Database size={16} />
                    <h3>Indexed Documents</h3>
                </div>

                {documents.length === 0 ? (
                    <div className="empty-docs">No documents uploaded yet.</div>
                ) : (
                    <ul className="doc-list">
                        {documents.map((doc) => (
                            <li key={doc.id} className="doc-item">
                                <FileText size={16} className="doc-icon" />
                                <div className="doc-details">
                                    <span className="doc-name">{doc.filename}</span>
                                    <span className="doc-date">{new Date(doc.created_at).toLocaleDateString()}</span>
                                </div>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </aside>
    );
};