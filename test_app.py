import io
import tempfile
import unittest
from pathlib import Path

import app as module
from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash
from PIL import Image
from flask_wtf.csrf import CSRFProtect


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Flask(__name__, template_folder=str(module.ROOT / 'templates'), static_folder=str(module.ROOT / 'assets'))
        self.app.config.update(TESTING=True, SECRET_KEY='test-only', SQLALCHEMY_DATABASE_URI='sqlite:///' + str(Path(self.directory.name) / 'test.db'), WTF_CSRF_ENABLED=False)
        module.db.init_app(self.app)
        CSRFProtect(self.app)
        self.original = module.app
        module.app = self.app
        manager = LoginManager(self.app)
        manager.login_view = 'sign_in'
        manager.user_loader(module.load_user)
        for rule in self.original.url_map.iter_rules():
            if rule.endpoint != 'static':
                self.app.add_url_rule(str(rule), rule.endpoint, self.original.view_functions[rule.endpoint], methods=rule.methods)
        self.context = self.app.app_context()
        self.context.push()
        module.db.create_all()
        module.db.session.add_all([
            module.User(username='owner', password_hash=generate_password_hash('testpassword1'), role='admin'),
            module.User(username='seller', password_hash=generate_password_hash('testpassword2'), role='seller'),
            module.Product(name='Vainilla', description='Prueba', price=70, image='productos/clasico-vainilla-v1.png', available=True),
        ])
        module.db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        module.db.session.remove()
        module.db.engine.dispose()
        self.context.pop()
        module.app = self.original
        self.directory.cleanup()

    def login(self, name):
        return self.client.post('/ingresar', data={'username': name, 'password': 'testpassword1' if name == 'owner' else 'testpassword2'})

    def test_visitor_catalog_and_panel_protection(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/panel').status_code, 302)
        self.assertEqual(self.client.post('/panel/productos/1/estado', data={'available': '0'}).status_code, 302)
        data = self.client.get('/api/catalogo').json
        self.assertEqual(data['whatsapp'], '59157002285')
        self.assertEqual(data['products'][0]['price'], '70.00')

    def test_seller_can_toggle_but_cannot_administer(self):
        self.assertEqual(self.login('seller').status_code, 302)
        self.assertEqual(self.client.get('/panel').status_code, 200)
        self.assertEqual(self.client.post('/panel/productos/1/estado', data={'available': '0'}).status_code, 302)
        self.assertEqual(self.client.get('/api/catalogo').json['products'], [])
        self.client.post('/panel/productos/1/estado', data={'available': '1'})
        self.assertEqual(len(self.client.get('/api/catalogo').json['products']), 1)
        for path in ['/panel/productos/1/editar', '/panel/productos/nuevo']:
            self.assertEqual(self.client.get(path).status_code, 403)
        for path in ['/panel/configuracion', '/panel/vendedores', '/panel/productos/1/eliminar']:
            self.assertEqual(self.client.post(path).status_code, 403)

    def test_owner_create_edit_delete_and_disable_seller(self):
        self.login('owner')
        image = io.BytesIO()
        Image.new('RGB', (30, 30), 'brown').save(image, 'PNG')
        image.seek(0)
        response = self.client.post('/panel/productos/nuevo', data={'name': 'Nuevo', 'description': 'Flan nuevo', 'price': '75.50', 'available': 'on', 'image': (image, 'photo.png')})
        self.assertEqual(response.status_code, 302)
        p = module.db.session.get(module.Product, 2)
        upload = module.ROOT / 'assets' / p.image
        self.addCleanup(lambda: upload.unlink(missing_ok=True))
        self.assertEqual(str(p.price), '75.50')
        self.assertEqual(self.client.get('/panel/productos/2/editar').status_code, 200)
        self.client.post('/panel/productos/2/editar', data={'name': 'Editado', 'description': 'Actualizado', 'price': '80.00', 'available': 'on'})
        self.assertEqual(module.db.session.get(module.Product, 2).name, 'Editado')
        self.client.post('/panel/vendedores/2/estado')
        self.client.post('/salir')
        self.assertEqual(self.login('seller').status_code, 200)
        self.assertEqual(self.client.get('/panel').status_code, 302)
        self.login('owner')
        self.client.post('/panel/productos/2/eliminar')
        self.assertIsNone(module.db.session.get(module.Product, 2))

    def test_real_app_rejects_posts_without_csrf(self):
        self.assertEqual(self.original.test_client().post('/ingresar', data={'username': 'x'}).status_code, 400)

    def test_decoration_price_permissions_validation_and_disable(self):
        self.login('owner')
        fields = {'name': 'Vainilla', 'description': 'Prueba', 'price': '70', 'available': 'on', 'decoration_enabled': 'on', 'decoration_price': '12.50'}
        self.assertEqual(self.client.post('/panel/productos/1/editar', data=fields).status_code, 302)
        self.assertEqual(self.client.get('/api/catalogo').json['products'][0]['decoration_price'], '12.50')
        self.assertIn(b'data-decoration="1"', self.client.get('/').data)
        for invalid in ['-1', 'NaN', 'Infinity', '1.001', '1000000', '']:
            fields['decoration_price'] = invalid
            self.assertEqual(self.client.post('/panel/productos/1/editar', data=fields).status_code, 200)
            self.assertEqual(str(module.db.session.get(module.Product, 1).decoration_price), '12.50')
        self.client.post('/salir')
        self.login('seller')
        self.assertEqual(self.client.post('/panel/productos/1/editar', data=fields).status_code, 403)
        self.client.post('/salir')
        self.login('owner')
        fields.pop('decoration_enabled')
        self.client.post('/panel/productos/1/editar', data=fields)
        self.assertIsNone(self.client.get('/api/catalogo').json['products'][0]['decoration_price'])
        self.assertNotIn(b'data-decoration="1"', self.client.get('/').data)


if __name__ == '__main__':
    unittest.main()
