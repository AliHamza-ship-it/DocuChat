import React, { useEffect, useState } from 'react';
import { DocumentUploader } from './DocumentUploader';
import api from '../api/client';
import { FileText, Database, PlusCircle, MessageSquare, Trash2 } from 'lucide-react';

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
            {/* New Chat Button */}
            <button className="new-chat-btn" onClick={onNewChat}>
                <PlusCircle size={18} />
                <span>New Chat</span>
            </button>

            {/* SECTION 1: Chat History */}
            <div className="sidebar-section chat-history-section">
                <div className="section-header">
                    <MessageSquare size={16} />
                    <h3>Chat History</h3>
                </div>

                <div className="chat-history-scroll">
                    {sessions.length === 0 ? (
                        <div className="empty-state">No past conversations</div>
                    ) : (
                        sessions.map((session) => (
                            <div
                                key={session.id}
                                className={`history-item ${session.id === activeSessionId ? 'active' : ''}`}
                                onClick={() => onSelectSession(session.id)}
                            >
                                <span className="history-title" title={session.title}>
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

            {/* SECTION 2: Document Management */}
            <div className="sidebar-section doc-section">
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
                                <li key={doc.id || doc.filename} className="doc-item">
                                    <FileText size={16} className="doc-icon" />
                                    <div className="doc-details">
                                        {/* Added inline style color: #000 (Black) to override CSS visibility issue */}
                                        <span className="doc-name" style={{ color: '#000', fontWeight: 'bold' }}>
                                            {doc.filename || doc.file_name || doc.name || doc.title || 'Document'}
                                        </span>
                                        <span className="doc-date" style={{ color: '#64748b', fontSize: '0.8rem' }}>
                                            {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : 'Uploaded'}
                                        </span>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            </div>
        </aside>
    );
};