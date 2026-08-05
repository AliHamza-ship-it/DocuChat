import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../api/client';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [token, setToken] = useState(localStorage.getItem('docuchat_token'));
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const storedUser = localStorage.getItem('docuchat_user');
        if (storedUser && token) {
            setUser(JSON.parse(storedUser));
        }
    }, [token]);

    const login = async (email, password) => {
        setLoading(true);
        try {
            const res = await api.post('/auth/login', { email, password });
            const { access_token, user: userData } = res.data;
            localStorage.setItem('docuchat_token', access_token);
            localStorage.setItem('docuchat_user', JSON.stringify(userData));
            setToken(access_token);
            setUser(userData);
            return { success: true };
        } catch (err) {
            return {
                success: false,
                error: err.response?.data?.detail || 'Login failed. Verify credentials or check email confirmation.'
            };
        } finally {
            setLoading(false);
        }
    };

    const register = async (userData) => {
        setLoading(true);
        try {
            const res = await api.post('/auth/register', userData);
            return { success: true, message: res.data.message };
        } catch (err) {
            return { success: false, error: err.response?.data?.detail || 'Registration failed.' };
        } finally {
            setLoading(false);
        }
    };

    const logout = () => {
        localStorage.removeItem('docuchat_token');
        localStorage.removeItem('docuchat_user');
        setToken(null);
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);