import requests
import json

print("=== TEST API LOCAL ===\n")

# Test 1: Registro o Login
print("1. Intentando login...")
login_data = {"username": "admin", "password": "admin123"}
r = requests.post("http://localhost:5000/api/auth/login", json=login_data)

if r.status_code == 401:
    print("   Usuario no existe, registrando...")
    r = requests.post("http://localhost:5000/api/auth/register", json=login_data)

if r.status_code in [200, 201]:
    token = r.json()["token"]
    print(f"   ✓ Token obtenido: {token[:20]}...")
    
    # Test 2: Crear item
    print("\n2. Creando item de prueba...")
    item_data = {
        "name": "Cable USB-C",
        "sku": "CABLE-001",
        "quantity": 50,
        "location": "Estante A",
        "price": 12.99,
        "costUnit": 8.50,
        "threshold": 10
    }
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post("http://localhost:5000/api/items", json=item_data, headers=headers)
    
    if r.status_code == 201:
        print("   ✓ Item creado exitosamente!")
        print(f"   Respuesta: {json.dumps(r.json(), indent=2)}")
        
        # Test 3: Listar items
        print("\n3. Listando todos los items...")
        r = requests.get("http://localhost:5000/api/items", headers=headers)
        items = r.json()
        print(f"   ✓ Total items en BD: {len(items)}")
        for item in items:
            print(f"   - {item['name']} (SKU: {item['sku']}, Qty: {item['quantity']})")
        
        print("\n=== CONCLUSIÓN: LA API FUNCIONA CORRECTAMENTE ✓ ===")
        print("El problema está en el FRONTEND (JavaScript no se ejecuta)")
    else:
        print(f"   ✗ Error al crear item: {r.status_code}")
        print(f"   {r.text}")
else:
    print(f"   ✗ Error de autenticación: {r.status_code}")
    print(f"   {r.text}")
