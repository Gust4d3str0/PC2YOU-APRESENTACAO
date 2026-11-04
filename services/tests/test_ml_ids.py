import pytest

from services.product_matching.ml_ids import extract_item_id, extract_product_id, is_mercado_livre_url, ml_ids_from_offer

PDP = 'https://www.mercadolivre.com.br/placa-de-video-gigabyte-geforce-rtx-5060-ti/p/MLB78085963'


def test_product_id_comes_from_the_p_path_only():
    assert extract_product_id(PDP) == 'MLB78085963'
    assert extract_product_id(PDP + '?pdp_filters=item_id%3AMLB7833387058&wid=MLB7833387058') == 'MLB78085963'
    assert extract_product_id('https://www.mercadolivre.com.br/up/MLBU123456789') is None
    assert extract_product_id('https://produto.mercadolivre.com.br/MLB-1234567890-placa-_JM') is None


def test_item_id_comes_from_wid_or_an_item_path_and_never_from_p():
    assert extract_item_id(PDP + '?wid=MLB7833387058') == 'MLB7833387058'
    assert extract_item_id(PDP + '?pdp_filters=item_id%3AMLB7833387058') == 'MLB7833387058'
    assert extract_item_id('https://produto.mercadolivre.com.br/MLB-1234567890-placa-de-video-_JM') == 'MLB1234567890'
    assert extract_item_id(PDP) is None                      # /p/MLB78085963 is a PRODUCT, not an item


def test_product_and_item_ids_stay_separate():
    url = PDP + '?wid=MLB7833387058'
    assert (extract_product_id(url), extract_item_id(url)) == ('MLB78085963', 'MLB7833387058')


def test_ambiguous_or_foreign_urls_give_none():
    assert extract_item_id('https://www.mercadolivre.com.br/x?wid=MLB1111111111', 'https://www.mercadolivre.com.br/y?wid=MLB2222222222') is None
    assert extract_product_id('https://www.mercadolivre.com.br/a/p/MLB11111111', 'https://www.mercadolivre.com.br/b/p/MLB22222222') is None
    assert extract_product_id('https://www.kabum.com.br/produto/p/MLB11111111') is None
    assert extract_item_id('https://example.com/?wid=MLB1111111111') is None
    assert extract_product_id(None, 42, '') is None


def test_affiliate_social_pages_and_short_links_carry_no_id():
    social = 'https://www.mercadolivre.com.br/social/creator?matt_word=x&ref=ABC123'
    assert (extract_product_id(social, 'https://meli.la/1bQQM46'), extract_item_id(social, 'https://meli.la/1bQQM46')) == (None, None)
    assert is_mercado_livre_url('https://meli.la/1bQQM46') and not is_mercado_livre_url('https://www.kabum.com.br/')


def test_ids_from_a_stored_offer_prefer_the_resolved_url_and_accept_both():
    offer = {'url': 'https://meli.la/abc', 'resolved_url': PDP + '?wid=MLB7833387058'}
    assert ml_ids_from_offer(offer) == ('MLB78085963', 'MLB7833387058')
    assert ml_ids_from_offer({'url': PDP}) == ('MLB78085963', None)
    assert ml_ids_from_offer(None) == (None, None)
