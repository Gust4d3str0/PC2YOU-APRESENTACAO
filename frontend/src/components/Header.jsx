import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Cpu, Heart, Moon, Search, Sun, Wrench } from 'lucide-react';
import { getStoredUser } from '../api';
import { DEMO } from '../demo';

export default function Header() {
  const [query, setQuery] = useState('');
  const [darkMode, setDarkMode] = useState(localStorage.getItem('darkMode') === 'true');
  const navigate = useNavigate();
  const location = useLocation();
  const user = getStoredUser();

  useEffect(() => {
    localStorage.setItem('darkMode', darkMode);
    document.documentElement.dataset.theme = darkMode ? 'dark' : 'light';
  }, [darkMode]);

  const handleSearch = (e) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/?q=${encodeURIComponent(query)}`);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('user');
    localStorage.removeItem('token');
    navigate('/login');
  };

  return (
    <header className="header">
      <div className="header-container">
        <Link to="/" className="logo" aria-label="Ir para a página inicial PC2YOU">
          <span className="logo-mark"><Cpu size={19} /></span>
          <span><strong>PC</strong>2YOU</span>
        </Link>
        
        <form className="search-bar" onSubmit={handleSearch}>
          <input
            type="text"
            className="search-input"
            placeholder="Buscar placas de vídeo, processadores, fontes..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="submit" className="icon-button" title="Buscar">
            <Search size={20} />
          </button>
        </form>

        <div className="nav-links">
          <Link to="/analyze-pc" className={`nav-link ${location.pathname === '/analyze-pc' ? 'is-active' : ''}`}>Analisar meu PC</Link>
          <Link to="/build" className={`nav-link nav-action ${location.pathname === '/build' ? 'is-active' : ''}`}>
            <Wrench size={17} />
            Montar PC
          </Link>
          {DEMO && <Link to="/apresentacao" className="nav-link nav-action">Apresentação</Link>}
          {!DEMO && <Link
            to="/favorites"
            className={`nav-link icon-only ${location.pathname === '/favorites' ? 'is-active' : ''}`}
            title="Favoritos"
            aria-label="Abrir favoritos"
          >
            <Heart size={19} />
          </Link>}
          <button 
            onClick={() => setDarkMode(!darkMode)} 
            className="icon-only"
            title="Alternar modo escuro"
            aria-label="Alternar modo escuro"
          >
            {darkMode ? <Sun size={20} /> : <Moon size={20} />}
          </button>
          
          {DEMO ? null : user ? (
            <>
              <span className="nav-link user-name">Olá, {user.name}</span>
              <button onClick={handleLogout} className="nav-link text-button">Sair</button>
            </>
          ) : (
            <>
              <Link to="/login" className={`nav-link ${location.pathname === '/login' ? 'is-active' : ''}`}>Entre</Link>
              <Link to="/register" className="btn-small">Criar conta</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
