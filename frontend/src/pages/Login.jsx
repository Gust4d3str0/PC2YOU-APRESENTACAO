import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import Header from '../components/Header';
import { getApiErrorMessage, usersApi } from '../api';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const res = await usersApi.post('/auth/login', { email, password });
      localStorage.setItem('user', JSON.stringify(res.data.user));
      localStorage.setItem('token', res.data.access_token);
      navigate('/');
    } catch (err) {
      setError(getApiErrorMessage(err, 'Erro ao fazer login'));
    }
  };

  return (
    <>
      <Header />
      <main className="auth-page">
        <section className="auth-visual">
          <span className="eyebrow">Área do cliente</span>
          <h1>Continue sua build de onde parou.</h1>
          <p>Favoritos, orçamento final e histórico de escolhas ficam prontos para a demonstração.</p>
        </section>
        <section className="auth-container">
          <h2>Entrar na PC2YOU</h2>
          {error && <div className="error-msg">{error}</div>}
          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label>E-mail</label>
              <input type="email" required className="form-input" value={email} onChange={e => setEmail(e.target.value)} />
            </div>
            <div className="form-group">
              <label>Senha</label>
              <input type="password" required className="form-input" value={password} onChange={e => setPassword(e.target.value)} />
            </div>
            <button type="submit" className="btn-primary">Continuar</button>
          </form>
          <p className="auth-link">
            Não tem conta? <Link to="/register">Crie aqui</Link>
          </p>
        </section>
      </main>
    </>
  );
}
