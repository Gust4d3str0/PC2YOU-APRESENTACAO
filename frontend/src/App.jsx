import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Login from './pages/Login';
import Register from './pages/Register';
import ComponentDetails from './pages/ComponentDetails';
import Favorites from './pages/Favorites';
import Build from './pages/Build';
import BudgetResult from './pages/BudgetResult';
import AnalyzePC from './pages/AnalyzePC';
import { DEMO } from './demo';

const Presentation = lazy(() => import('./presentation/Presentation'));

function App() {
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/components/:id" element={<ComponentDetails />} />
        <Route path="/build" element={<Build />} />
        <Route path="/analyze-pc" element={<AnalyzePC />} />
        {DEMO ? (
          <Route path="/apresentacao" element={<Suspense fallback={<p style={{ padding: 24 }}>Carregando apresentação…</p>}><Presentation /></Suspense>} />
        ) : (
          <>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/favorites" element={<Favorites />} />
            <Route path="/budget/:id" element={<BudgetResult />} />
          </>
        )}
      </Routes>
    </Router>
  );
}

export default App;
