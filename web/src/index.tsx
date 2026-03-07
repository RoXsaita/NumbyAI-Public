// Entry point for NumbyAI standalone app
import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';

// Mount app component
const rootElement = document.getElementById('root') || document.body;
const root = createRoot(rootElement);
root.render(<App />);
