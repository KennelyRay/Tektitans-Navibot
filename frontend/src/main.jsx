import { createRoot } from 'react-dom/client';
import ChatWidget from './ChatWidget.jsx';

const container = document.getElementById('navibot-root');
if (container) {
    createRoot(container).render(<ChatWidget />);
}
