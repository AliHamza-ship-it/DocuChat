import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, Sparkles } from 'lucide-react';

export const Navbar = () => {
    const { user, logout } = useAuth();

    return (
        <header className="navbar">
            <div className="nav-brand">
                <div className="brand-icon">
                    <Sparkles size={20} />
                </div>
                <span className="brand-title">
                    DocuChat <span className="badge">AI RAG</span>
                </span>
            </div>

            {user && (
                <div className="nav-user">
                    <span className="user-email">
                        {user?.email || user?.name || 'Logged In User'}
                    </span>
                    <button className="btn-logout" onClick={logout} title="Sign Out">
                        <LogOut size={15} />
                        <span>Logout</span>
                    </button>
                </div>
            )}
        </header>
    );
};