import React from 'react';
import ReactDOM from 'react-dom/client';
import App, { GlobalDataProvider } from './App';
import './index.css';
import * as serviceWorker from './serviceWorker';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <GlobalDataProvider>
      <App />
    </GlobalDataProvider>
  </React.StrictMode>
);

serviceWorker.register();
