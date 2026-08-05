import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Sparkles, ArrowRight, ShieldCheck, Mail, Lock, User, Globe } from 'lucide-react';

export const AuthPage = () => {
    const [isLogin, setIsLogin] = useState(true);
    const { login, register, loading } = useAuth();

    const [formData, setFormData] = useState({
        email: '',
        password: '',
        name: '',
        age: '',
        country: 'Pakistan'
    });

    const [error, setError] = useState(null);
    const [info, setInfo] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);
        setInfo(null);

        if (isLogin) {
            const res = await login(formData.email, formData.password);
            if (!res.success) setError(res.error);
        } else {
            const res = await register(formData);
            if (res.success) {
                setInfo(res.message);
                setIsLogin(true);
            } else {
                setError(res.error);
            }
        }
    };

    return (
        <div className="auth-wrapper">
            <div className="auth-card">
                <div className="auth-header">
                    <div className="brand-badge"><Sparkles size={20} /> DocuChat</div>
                    <h2>{isLogin ? "Welcome Back" : "Create Account"}</h2>
                    <p>{isLogin ? "Sign in to query your knowledge base" : "Register to start indexing documents"}</p>
                </div>

                {error && <div className="alert alert-danger">{error}</div>}
                {info && <div className="alert alert-info">{info}</div>}

                <form onSubmit={handleSubmit} className="auth-form">
                    {!isLogin && (
                        <>
                            <div className="form-group">
                                <label><User size={14} /> Full Name</label>
                                <input
                                    type="text"
                                    required
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    placeholder="Ali Hamza"
                                />
                            </div>

                            <div className="form-row">
                                <div className="form-group">
                                    <label>Age</label>
                                    <input
                                        type="number"
                                        required
                                        value={formData.age}
                                        onChange={(e) => setFormData({ ...formData, age: parseInt(e.target.value) })}
                                    />
                                </div>
                                <div className="form-group">
                                    <label><Globe size={14} /> Country</label>
                                    <input
                                        type="text"
                                        required
                                        value={formData.country}
                                        onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                                    />
                                </div>
                            </div>
                        </>
                    )}

                    <div className="form-group">
                        <label><Mail size={14} /> Email Address</label>
                        <input
                            type="email"
                            required
                            value={formData.email}
                            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                            placeholder="user@company.com"
                        />
                    </div>

                    <div className="form-group">
                        <label><Lock size={14} /> Password</label>
                        <input
                            type="password"
                            required
                            value={formData.password}
                            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                            placeholder="••••••••"
                        />
                    </div>

                    <button type="submit" className="btn-primary btn-full btn-glow mt-2" disabled={loading}>
                        {loading ? "Processing..." : (isLogin ? "Sign In" : "Register")} <ArrowRight size={16} />
                    </button>
                </form>

                <div className="auth-footer">
                    <button className="btn-link" onClick={() => { setIsLogin(!isLogin); setError(null); }}>
                        {isLogin ? "Need an account? Register" : "Already registered? Sign in"}
                    </button>
                </div>
            </div>
        </div>
    );
};