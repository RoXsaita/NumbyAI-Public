/**
 * Main App Component - Simple Automatic Workflow
 * 
 * Just upload a statement and get your dashboard. No chat UI needed!
 */
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom';
import { SimpleUpload } from './components/SimpleUpload';
import { DashboardWidget } from './widgets/dashboard';
import { ErrorBoundary } from './components/ErrorBoundary';

const DashboardPage: React.FC = () => {
  return (
    <ErrorBoundary>
      <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '16px' }}>
          <Link
            to="/"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              padding: '8px 16px', backgroundColor: '#dc2626', color: 'white',
              borderRadius: '8px', textDecoration: 'none', fontSize: '13px', fontWeight: 600,
              transition: 'background-color 0.15s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#b91c1c')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#dc2626')}
          >
            <span style={{ fontSize: '15px' }}>+</span>
            Upload Statement
          </Link>
        </div>
        <DashboardWidget />
      </div>
    </ErrorBoundary>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SimpleUpload />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
