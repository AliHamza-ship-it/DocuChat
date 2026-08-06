import React from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { AuthPage } from './pages/AuthPage';
import { ChatPage } from './pages/ChatPage';

const AppContent = () => {
  const { token, user } = useAuth();

  // Strict guard: requires both a valid token and a loaded user object
  return (token && user) ? <ChatPage /> : <AuthPage />;
};

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}