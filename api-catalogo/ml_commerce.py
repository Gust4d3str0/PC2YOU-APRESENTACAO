"""Official ML OAuth/read client. No credentials or provider response bodies in logs."""
import json
import logging
import os
from pathlib import Path
from threading import RLock
import time
import requests

log = logging.getLogger('pc2you.ml')


class MLUnavailable(RuntimeError):
    pass


class MercadoLivreClient:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.lock = RLock()
        self.tokens = {}
        self.cache = {}
        self.status = 'not_checked'
        self.checked_until = 0
        path = os.getenv('MERCADO_LIVRE_TOKEN_FILE')
        if path and Path(path).is_file():
            self.tokens = json.loads(Path(path).read_text(encoding='utf-8'))

    def token(self, key):
        return self.tokens.get(key) or os.getenv('MERCADO_LIVRE_' + key.upper(), '')

    def refresh(self):
        with self.lock:
            payload = {'grant_type': 'refresh_token', 'refresh_token': self.token('refresh_token'),
                       'client_id': os.getenv('MERCADO_LIVRE_CLIENT_ID', ''),
                       'client_secret': os.getenv('MERCADO_LIVRE_CLIENT_SECRET', '')}
            if not all(payload.values()):
                self.status = 'authentication_required'
                raise MLUnavailable('Mercado Livre: autorização necessária.')
            try:
                r = self.session.post('https://api.mercadolibre.com/oauth/token', data=payload, timeout=(3, 10))
                if r.status_code != 200:
                    raise MLUnavailable('Mercado Livre: renovação indisponível.')
                data = r.json()
                if not data.get('access_token') or not data.get('refresh_token'):
                    raise MLUnavailable('Mercado Livre: credencial incompleta.')
                self.tokens = {'access_token': data['access_token'], 'refresh_token': data['refresh_token'],
                               'expires_at': time.time() + data.get('expires_in', 0)}
                path = os.getenv('MERCADO_LIVRE_TOKEN_FILE')
                if path:
                    target = Path(path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_suffix('.tmp')
                    temporary.write_text(json.dumps(self.tokens), encoding='utf-8')
                    temporary.chmod(0o600)
                    temporary.replace(target)
                log.info('ML token refreshed')
            except (requests.RequestException, ValueError, OSError) as exc:
                raise MLUnavailable('Mercado Livre: renovação indisponível.') from exc

    def get(self, path, params=None, ttl=0):
        if not path.startswith('/') or '..' in path:
            raise MLUnavailable('Recurso inválido.')
        key = (path, json.dumps(params or {}, sort_keys=True))
        with self.lock:
            cached = self.cache.get(key)
            if cached and cached[0] > time.monotonic():
                return 200, cached[1]
            if self.tokens.get('expires_at') and self.tokens['expires_at'] <= time.time()+30:
                self.refresh()
            if not self.token('access_token'):
                self.status = 'authentication_required'
                raise MLUnavailable('Mercado Livre: autorização necessária.')
            try:
                for attempt in range(2):
                    response = self.session.get('https://api.mercadolibre.com' + path, params=params,
                        headers={'Authorization': 'Bearer ' + self.token('access_token')}, timeout=(3, 10))
                    if response.status_code != 401 or attempt:
                        break
                    self.refresh()
                code = response.status_code
                self.status = 'available' if code == 200 else 'rate_limited' if code == 429 else 'unavailable'
                log.info('ML auth OK' if code == 200 else 'ML rate limited' if code == 429 else 'ML unavailable')
                if code == 200 and path == '/products/search':
                    log.info('ML search success')
                data = response.json() if code == 200 else None
                if code == 200 and ttl:
                    if len(self.cache) >= 512:
                        self.cache.clear()
                    self.cache[key] = (time.monotonic()+ttl, data)
                return code, data
            except (requests.RequestException, ValueError) as exc:
                self.status = 'unavailable'
                log.warning('ML unavailable')
                raise MLUnavailable('Mercado Livre temporariamente indisponível.') from exc

    def public_status(self):
        return {'source': 'mercado_livre', 'configured': bool(self.token('access_token')),
                'status': self.status, 'message': 'Mercado Livre disponível' if self.status == 'available'
                else 'Mercado Livre temporariamente indisponível' if self.status in {'unavailable', 'rate_limited'}
                else 'Mercado Livre: autorização necessária' if self.status == 'authentication_required'
                else 'Mercado Livre aguardando validação de acesso'}

    def check_access(self):
        if self.checked_until < time.monotonic():
            self.checked_until = time.monotonic()+300
            try:
                self.get('/users/me', ttl=300)
            except MLUnavailable:
                pass
        return self.public_status()


class MercadoLivrePriceService:
    def __init__(self, client):
        self.client = client

    def current(self, item_id):
        if not isinstance(item_id, str) or not __import__('re').fullmatch(r'MLB\d+', item_id):
            return None
        status, data = self.client.get(f'/items/{item_id}/sale_price', {'context': 'channel_marketplace'}, ttl=180)
        if status != 200 or not isinstance(data, dict) or data.get('currency_id') != 'BRL':
            return None
        from product_matching.quality import money
        if money(data.get('amount')) is None:
            return None
        log.info('ML price success')
        return {'price': money(data['amount']), 'regular_price': money(data.get('regular_amount')),
                'currency': data['currency_id'], 'valid_until': (data.get('conditions') or {}).get('end_time'),
                'source': 'mercado_livre'}


client = MercadoLivreClient()
