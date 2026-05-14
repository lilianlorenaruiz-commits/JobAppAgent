import sqlite3
conn = sqlite3.connect(r"C:\Users\lilia\Clientes\Lorena Ruiz\JobAppAgent\database\job_app.db")
conn.execute("DELETE FROM memoria_cargos")
conn.execute("DELETE FROM aplicaciones")
conn.commit()
print("DB reseteada para test")
