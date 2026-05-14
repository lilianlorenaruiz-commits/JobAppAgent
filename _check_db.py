import sqlite3
conn = sqlite3.connect(r"C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent\database\job_app.db")
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tablas:", [r[0] for r in c.fetchall()])
c.execute("SELECT COUNT(*) FROM aplicaciones")
print("Aplicaciones registradas:", c.fetchone()[0])
c.execute("SELECT rama, cargo, empresa, resultado, fecha_creacion FROM aplicaciones ORDER BY fecha_creacion DESC LIMIT 10")
rows = c.fetchall()
if rows:
    for r in rows:
        print(r)
else:
    print("DB vacía — ningún run completó el pipeline")
conn.close()
