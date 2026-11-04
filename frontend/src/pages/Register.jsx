import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import Header from '../components/Header';
import { getApiErrorMessage, usersApi } from '../api';

export default function Register() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleRegister = async (e) => {
    e.preventDefault();
    try {
      await usersApi.post('/auth/register', { name, email, password });
      const loginRes = await usersApi.post('/auth/login', { email, password });
      localStorage.setItem('user', JSON.stringify(loginRes.data.user));
      localStorage.setItem('token', loginRes.data.access_token);
      navigate('/');
    } catch (err) {
      setError(getApiErrorMessage(err, 'Erro ao criar conta'));
    }
  };

  return (
    <>
      <Header />
      <main className="auth-page">
        <section className="auth-visual">
          <span className="eyebrow">Comece agora</span>
          <h1>Salve peças e gere orçamentos com links por loja.</h1>
          <p>Uma conta simples já libera favoritos e uma montagem guiada para apresentação.</p>
        </section>
        <section className="auth-container">
          <h2>Criar conta na PC2YOU</h2>
          {error && <div className="error-msg">{error}</div>}
          <form onSubmit={handleRegister}>
            <div className="form-group">
              <label>Nome completo</label>
              <input type="text" required className="form-input" value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div className="form-group">
              <label>E-mail</label>
              <input type="email" required className="form-input" value={email} onChange={e => setEmail(e.target.value)} />
            </div>
            <div className="form-group">
              <label>Senha</label>
              <input type="password" required className="form-input" value={password} onChange={e => setPassword(e.target.value)} />
            </div>
            <button type="submit" className="btn-primary">Criar conta</button>
          </form>
          <p className="auth-link">
            Já tem conta? <Link to="/login">Entre</Link>
          </p>
        </section>
      </main>
    </>
  );
}
