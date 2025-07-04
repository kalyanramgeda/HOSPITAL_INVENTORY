from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'Kalyan_ram_geda'
CORS(app)

# Initialize DB
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # User table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            name TEXT NOT NULL
        )
    ''')

    # Items table
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            current_stock INTEGER,
            min_stock INTEGER,
            unit TEXT,
            supplier TEXT,
            last_ordered TIMESTAMP
        )
    ''')

    # Orders table
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            supplier TEXT NOT NULL,
            urgency TEXT CHECK(urgency IN ('low', 'normal', 'high', 'critical')),
            status TEXT CHECK(status IN ('pending', 'approved', 'shipped', 'delivered', 'cancelled')),
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expected_delivery DATE,
            notes TEXT,
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    ''')

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Routes
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    phone = request.form['phone']
    name = request.form['name']

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE phone=? AND name=?", (phone, name))
    user = c.fetchone()

    if not user:
        c.execute("INSERT INTO users (phone, name) VALUES (?, ?)", (phone, name))
        conn.commit()

    conn.close()

    session['username'] = name  # ✅ Store in session
    return redirect(url_for('dashboard'))


    
@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('home'))

    conn = get_db_connection()
    c = conn.cursor()

    # Total items count
    c.execute("SELECT COUNT(*) FROM items")
    total_items = c.fetchone()[0]

    # Category count
    c.execute("SELECT COUNT(DISTINCT category) FROM items")
    category_count = c.fetchone()[0]

    # Low stock count
    c.execute("SELECT COUNT(*) FROM items WHERE current_stock < min_stock")
    low_stock_count = c.fetchone()[0]

    # Fetch top 6 items for preview
    c.execute("SELECT * FROM items ORDER BY id DESC LIMIT 6")
    items = c.fetchall()

    # Fetch top 4 recent orders
    c.execute('''
        SELECT o.*, i.name as item_name, i.unit 
        FROM orders o
        JOIN items i ON o.item_id = i.id
        ORDER BY o.order_date DESC
        LIMIT 4
    ''')
    orders = c.fetchall()

    # Fetch low stock / out-of-stock items for alerts
    c.execute('''
        SELECT name, current_stock, min_stock
        FROM items
        WHERE current_stock = 0 OR current_stock < min_stock
        ORDER BY current_stock ASC
        LIMIT 4
    ''')
    alerts = c.fetchall()

    conn.close()

    return render_template(
        'dashboard.html',
        name=session['username'],
        total_items=total_items,
        category_count=category_count,
        low_stock_count=low_stock_count,
        items=items,
        orders=orders,
        alerts=alerts
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/users')
def show_users():
    conn = get_db_connection()
    users = conn.execute("SELECT phone, name FROM users").fetchall()
    conn.close()
    return "<br>".join([f"Phone: {u['phone']}, Name: {u['name']}" for u in users])

@app.route('/inventory')
def inventory():
    return render_template('inventory.html')

@app.route('/medical-supplies')
def medical_supplies():
    return render_template('medical_supplies.html')

@app.route('/order')
def order():
    return render_template('order.html')

@app.route('/settings')
def settings():
    return render_template('setting.html')
@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

# Inventory API
@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    conn = get_db_connection()
    items = conn.execute('SELECT * FROM items').fetchall()
    conn.close()
    return jsonify([dict(item) for item in items])

@app.route('/api/inventory', methods=['POST'])
def create_inventory_item():
    data = request.get_json()
    required_fields = ['name', 'category', 'current_stock', 'min_stock', 'unit', 'supplier']

    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing fields'}), 400

    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO items (name, category, current_stock, min_stock, unit, supplier)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data['category'],
            data['current_stock'],
            data['min_stock'],
            data['unit'],
            data['supplier']
        ))
        conn.commit()
        return jsonify({'message': 'Item added successfully'}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/inventory/<int:item_id>', methods=['PUT'])
def update_inventory_item(item_id):
    data = request.get_json()
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE items SET
                name = ?,
                category = ?,
                current_stock = ?,
                min_stock = ?,
                unit = ?,
                supplier = ?
            WHERE id = ?
        ''', (
            data['name'],
            data['category'],
            data['current_stock'],
            data['min_stock'],
            data['unit'],
            data['supplier'],
            item_id
        ))
        conn.commit()
        return jsonify({'message': 'Item updated'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/inventory/<int:item_id>', methods=['DELETE'])
def delete_inventory_item(item_id):
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
        conn.commit()
        return jsonify({'message': 'Item deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/inventory/<int:item_id>/update-stock', methods=['POST'])
def update_inventory_stock(item_id):
    data = request.get_json()
    action = data.get('action')
    quantity = int(data.get('quantity', 0))

    if action not in ['restock', 'use']:
        return jsonify({'error': 'Invalid action'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT current_stock FROM items WHERE id = ?', (item_id,))
    result = cursor.fetchone()

    if not result:
        return jsonify({'error': 'Item not found'}), 404

    current_stock = result['current_stock']
    new_stock = current_stock + quantity if action == 'restock' else max(0, current_stock - quantity)

    cursor.execute('UPDATE items SET current_stock = ? WHERE id = ?', (new_stock, item_id))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Stock updated'})

# Orders API
@app.route('/api/orders', methods=['GET'])
def get_orders():
    conn = get_db_connection()
    orders = conn.execute('''
        SELECT o.*, i.name as item_name, i.unit 
        FROM orders o
        JOIN items i ON o.item_id = i.id
        ORDER BY o.order_date DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(order) for order in orders])

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    required_fields = ['item_id', 'quantity', 'supplier', 'urgency']

    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO orders (item_id, quantity, supplier, urgency, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['item_id'],
            data['quantity'],
            data['supplier'],
            data.get('urgency', 'normal'),
            'pending',
            data.get('notes', '')
        ))
        order_id = cursor.lastrowid

        conn.execute('UPDATE items SET last_ordered = CURRENT_TIMESTAMP WHERE id = ?', (data['item_id'],))
        conn.commit()
        return jsonify({"message": "Order created", "id": order_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/orders/<int:order_id>', methods=['PUT'])
def update_order_status(order_id):
    data = request.get_json()
    if 'status' not in data:
        return jsonify({"error": "Status is required"}), 400

    valid_statuses = ['pending', 'approved', 'shipped', 'delivered', 'cancelled']
    if data['status'] not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400

    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', (data['status'], order_id))
    conn.commit()

    if data['status'] == 'delivered':
        order = conn.execute('SELECT item_id, quantity FROM orders WHERE id = ?', (order_id,)).fetchone()
        conn.execute('UPDATE items SET current_stock = current_stock + ? WHERE id = ?', (order['quantity'], order['item_id']))
        conn.commit()

    conn.close()
    return jsonify({"message": "Order status updated"})

# Main
if __name__ == '__main__':
    if not os.path.exists('database.db'):
        init_db()
    else:
        init_db()

    app.run(debug=True, threaded=True)
