import React, { useEffect, useState } from 'react';
import { DocumentUploader } from './DocumentUploader';
import api from '../api/client';
import {
    FileText,
    Database,
    PlusCircle,
    MessageSquare,
    Trash2
} from 'lucide-react';

export const Sidebar = ({
    refreshTrigger,
    onUploadSuccess,
    sessions = [],
    activeSessionId,
    onSelectSession,
    onNewChat,
    onDeleteSession
}) => {
    const [documents, setDocuments] = useState([]);
    const [deletingDocumentId, setDeletingDocumentId] = useState(null);

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

    const handleDeleteDocument = async (documentId, filename) => {
        const confirmed = window.confirm(
            `Are you sure you want to delete "${filename}"?\n\nThis will remove the document and its indexed chunks.`
        );

        if (!confirmed) {
            return;
        }

        try {
            setDeletingDocumentId(documentId);

            await api.delete(`/docs/${documentId}`);

            setDocuments((prev) =>
                prev.filter((doc) => doc.id !== documentId)
            );

            if (onUploadSuccess) {
                onUploadSuccess();
            }
        } catch (err) {
            console.error('Failed to delete document', err);

            window.alert(
                err.response?.data?.detail ||
                'Failed to delete the document. Please try again.'
            );
        } finally {
            setDeletingDocumentId(null);
        }
    };

    return (
        <aside className="sidebar">
            <button className="new-chat-btn" onClick={onNewChat}>
                <PlusCircle size={18} />
                <span>New Chat</span>
            </button>

            <div className="sidebar-section chat-history-section">
                <div className="section-header">
                    <MessageSquare size={16} />
                    <h3>Chat History</h3>
                </div>

                <div className="chat-history-scroll">
                    {sessions.length === 0 ? (
                        <div
                            className="empty-state"
                            style={{
                                color: 'var(--text-muted)',
                                fontSize: '0.85rem'
                            }}
                        >
                            No past conversations
                        </div>
                    ) : (
                        sessions.map((session) => (
                            <div
                                key={session.id}
                                className={`history-item ${session.id === activeSessionId
                                        ? 'active'
                                        : ''
                                    }`}
                                onClick={() =>
                                    onSelectSession(session.id)
                                }
                            >
                                <span
                                    className="history-title"
                                    title={session.title}
                                >
                                    {session.title || 'Untitled Chat'}
                                </span>

                                <button
                                    className="delete-btn"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onDeleteSession(session.id);
                                    }}
                                    title="Delete session"
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        ))
                    )}
                </div>
            </div>

            <hr className="sidebar-divider" />

            <div className="sidebar-section doc-section">
                <DocumentUploader
                    onUploadSuccess={() => {
                        fetchDocuments();

                        if (onUploadSuccess) {
                            onUploadSuccess();
                        }
                    }}
                />

                <div
                    className="doc-library"
                    style={{ marginTop: '1.5rem' }}
                >
                    <div className="doc-library-header">
                        <Database size={16} />
                        <h3>Indexed Documents</h3>
                    </div>

                    {documents.length === 0 ? (
                        <div
                            className="empty-docs"
                            style={{
                                color: 'var(--text-muted)',
                                fontSize: '0.85rem',
                                marginTop: '0.5rem'
                            }}
                        >
                            No documents uploaded yet.
                        </div>
                    ) : (
                        <ul
                            className="doc-list"
                            style={{
                                listStyle: 'none',
                                padding: 0
                            }}
                        >
                            {documents.map((doc) => {
                                const filename =
                                    doc.filename ||
                                    doc.file_name ||
                                    doc.name ||
                                    doc.title ||
                                    'Document';

                                const isDeleting =
                                    deletingDocumentId === doc.id;

                                return (
                                    <li
                                        key={
                                            doc.id ||
                                            doc.filename
                                        }
                                        className="doc-item"
                                    >
                                        <FileText
                                            size={16}
                                            className="doc-icon"
                                        />

                                        <div
                                            className="doc-details"
                                            style={{
                                                display: 'flex',
                                                flexDirection: 'column'
                                            }}
                                        >
                                            <span
                                                className="doc-name"
                                                title={filename}
                                            >
                                                {filename}
                                            </span>

                                            <span className="doc-date">
                                                {doc.created_at
                                                    ? new Date(
                                                        doc.created_at
                                                    ).toLocaleDateString()
                                                    : 'Uploaded'}
                                            </span>
                                        </div>

                                        <button
                                            className="delete-btn"
                                            onClick={() =>
                                                handleDeleteDocument(
                                                    doc.id,
                                                    filename
                                                )
                                            }
                                            disabled={isDeleting}
                                            title="Delete document"
                                            aria-label={`Delete ${filename}`}
                                        >
                                            <Trash2
                                                size={14}
                                                className={
                                                    isDeleting
                                                        ? 'animate-pulse'
                                                        : ''
                                                }
                                            />
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
            </div>
        </aside>
    );
};