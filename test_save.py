#!/usr/bin/env python3
"""Test que el sistema guarda items correctamente"""
import uuid

import requests

BASE = 'http://localhost:5000/api'

print("\n" + "="*50)
print("PRUEBA DE GUARDADO DE ITEMS")
print("="*50)

# 1. Register new user
print('\n1️⃣ Creando o autenticando usuario de test...')
username = f"testuser-{uuid.uuid4().hex[:8]}"
credentials = {
    'username': username,
    'password': 'test1234',
    'email': f'{username}@example.com'
}

resp = requests.post(f'{BASE}/auth/register', json=credentials)
register_data = resp.json() if resp.headers.get('Content-Type', '').startswith('application/json') else {}

if resp.status_code in (200, 201) and register_data.get('token'):
    token = register_data['token']
    print('✓ Usuario listo')
    print(f'  Usuario: {username}')
    print(f'  Token: {token[:12]}...')
elif resp.status_code in (200, 201) and register_data.get('requiresVerification'):
    print('⚠️ Registro requiere verificación por correo.')
    print('  Verifica el email recibido y luego ejecuta esta prueba con un usuario ya verificado.')
    exit(1)
else:
    print(f'  Registro resultó en ({resp.status_code}), intentando login...')
    login_resp = requests.post(
        f'{BASE}/auth/login',
        json={'username': credentials['username'], 'password': credentials['password']}
    )
    if login_resp.status_code == 200:
        token = login_resp.json()['token']
        print('✓ Login exitoso')
        print(f'  Usuario: {username}')
        print(f'  Token: {token[:12]}...')
    else:
        print(f'✗ Error de autenticación: {login_resp.status_code}')
        print(f'  {login_resp.text}')
        exit(1)

# 2. Create item
print('\n2️⃣ Agregando item al inventario...')
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
item_data = {
    'name': 'TEST GUARDADO',
    'sku': f"TEST-SAVE-{uuid.uuid4().hex[:8].upper()}",
    'quantity': 25,
    'location': 'Almacén',
    'price': 150.00,
    'costUnit': 75.00,
    'threshold': 5
}
resp = requests.post(f'{BASE}/items', json=item_data, headers=headers)
if resp.status_code == 201:
    item = resp.json()
    print(f'✓ Item creado exitosamente')
    print(f'  Nombre: {item["name"]}')
    print(f'  ID: {item["id"][:8]}...')
    print(f'  Cantidad: {item["quantity"]}')
else:
    print(f'✗ Error al crear item: {resp.status_code}')
    print(f'  {resp.text}')
    exit(1)

# 3. Verify item exists
print('\n3️⃣ Verificando que se guardó en la base de datos...')
resp = requests.get(f'{BASE}/items', headers=headers)
if resp.status_code == 200:
    items = resp.json()
    print(f'  Total items en BD: {len(items)}')
    found = [i for i in items if i['name'] == 'TEST GUARDADO']
    if found:
        print(f'✓ ¡ITEM ENCONTRADO EN LA BD!')
        item = found[0]
        print(f'\n  Datos guardados:')
        print(f'    • Nombre: {item["name"]}')
        print(f'    • SKU: {item["sku"]}')
        print(f'    • Cantidad: {item["quantity"]}')
        print(f'    • Ubicación: {item["location"]}')
        print(f'    • Precio: ${item["price"]}')
        print(f'    • Costo: ${item["costUnit"]}')
    else:
        print(f'✗ Item NO encontrado en la BD')
        print(f'  Items en BD: {[i["name"] for i in items]}')
else:
    print(f'✗ Error: {resp.text}')

print('\n' + "="*50)
print("✅ PRUEBA COMPLETADA")
print("="*50 + "\n")
