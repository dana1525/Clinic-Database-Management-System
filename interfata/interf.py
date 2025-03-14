from flask import Flask, render_template, request, redirect, url_for
from flask_cors import CORS
import cx_Oracle

dsn = cx_Oracle.makedsn("DESKTOP-IQT5LOP", 1521, sid="XE")
connection = cx_Oracle.connect(user="C##demouser", password="demouser", dsn=dsn)

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/list/<table>", methods=["GET", "POST"])
def list_table_data(table):
    cursor = connection.cursor()

    query = f"SELECT * FROM {table.upper()}"
    order_by_column = request.form.get('column')
    order_direction = request.form.get('order', 'ASC')
    if order_by_column and order_direction:
        query += f" ORDER BY {order_by_column} {order_direction}"

    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [i[0] for i in cursor.description]

    cursor.close()
    return render_template("table.html", table=table, columns=columns, rows=rows)


def get_primary_key_columns(table):
    query = f"""
    SELECT column_name
    FROM all_cons_columns
    WHERE constraint_name = (
        SELECT constraint_name
        FROM all_constraints
        WHERE table_name = :table_name AND constraint_type = 'P'
    )
    """
    cursor = connection.cursor()
    cursor.execute(query, {"table_name": table.upper()})
    pk_column = cursor.fetchone()[0]
    cursor.close()
    return pk_column


@app.route("/edit/<table>/<int:record_id>", methods=["GET", "POST"])
def edit_record(table, record_id):
    if request.method == "GET":
        primary_key = get_primary_key_columns(table)
        query = f"SELECT * FROM {table.upper()} WHERE {primary_key} = :record_id"
    
        cursor = connection.cursor()
        cursor.execute(query, {"record_id": record_id})
        record = cursor.fetchone()
    
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        return render_template("edit_record.html", table=table, record=record, columns=columns, record_id=record_id)

    if request.method == "POST":
        primary_key = get_primary_key_columns(table)
        
        updates = {}
        for key, value in request.form.items():
            if "data" in key.lower():  # Verificăm dacă este un câmp de dată
                updates[key] = f"TO_DATE('{value}', 'YYYY-MM-DD HH24:MI:SS')"  # Conversie Oracle
            else:
                updates[key] = value


        set_clause = ", ".join(f"{column} = {updates[column]}" if "data" in column.lower() else f"{column} = :{column}"
        for column in updates if column != primary_key)

        where_clause = f"{primary_key} = :{primary_key}"

        update_query = f"UPDATE {table.upper()} SET {set_clause} WHERE {where_clause}"
    
        cursor = connection.cursor()
        cursor.execute(update_query, updates)
        connection.commit()
        cursor.close()
        return redirect(url_for("list_table_data", table=table))


@app.route("/delete/<table>/<int:record_id>", methods=["POST"])
def delete_record(table, record_id):

    primary_key = get_primary_key_columns(table)
    delete_query = f"DELETE FROM {table.upper()} WHERE {primary_key} = :record_id"
    
    cursor = connection.cursor()
    cursor.execute(delete_query, {"record_id": record_id})
    connection.commit()
    cursor.close()
    return redirect(url_for("list_table_data", table=table))


@app.route("/punctul_c", methods=["GET"])
def punctul_c():
    query = f"""SELECT * FROM PACIENT P
    JOIN DIAGNOSTIC D ON P.CNP_PACIENT = D.CNP_PACIENT
    JOIN TRATAMENT T ON D.ID_DIAGNOSTIC = T.ID_DIAGNOSTIC
    WHERE UPPER(T.NUME_TRATAMENT) LIKE 'ANTIVIRALE%'
    AND D.DATA_DIAGNOSTICARE >= ADD_MONTHS(SYSDATE, -24)"""
    cursor = connection.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    cursor.close()
    return render_template("punctul_c.html", rows=rows, columns=columns)


@app.route("/punctul_d", methods=["GET"])
def punctul_d():
    query = f"""SELECT P.CNP_PACIENT, P.NUME_PACIENT, P.PRENUME_PACIENT, COUNT(ID_ANALIZA)
    FROM PACIENT P JOIN ANALIZA A
    ON P.CNP_PACIENT = A.CNP_PACIENT
    GROUP BY P.CNP_PACIENT, P.NUME_PACIENT, P.PRENUME_PACIENT
    HAVING COUNT(A.ID_ANALIZA) >= 2"""
    cursor = connection.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    cursor.close()
    return render_template("punctul_d.html", rows=rows, columns=columns)

@app.route("/viz_compusa", methods=["GET"])
def viz_compusa():
    viz_compusa = f"""CREATE OR REPLACE VIEW DOCTORI_DEPARTAMENTE AS(
    SELECT DE.ID_DEPARTAMENT, DE.NUME_DEPARTAMENT, DO.CNP_DOCTOR, DO.NUME_DOCTOR, DO.PRENUME_DOCTOR, DO.SPECIALIZARE, DO.NR_TELEFON
    FROM DOCTOR DO JOIN DEPARTAMENT DE
    ON DO.ID_DEPARTAMENT = DE.ID_DEPARTAMENT
    )"""
    cursor = connection.cursor()
    cursor.execute(viz_compusa)
    cursor.execute("SELECT * FROM DOCTORI_DEPARTAMENTE")
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    cursor.close()
    return render_template("viz_compusa.html", rows=rows, columns=columns)
    
@app.route("/viz_complexa", methods=["GET"])
def viz_complexa():
    viz_complexa = f"""CREATE OR REPLACE VIEW COST_TOTAL_PACIENT AS (
    SELECT P.CNP_PACIENT, P.NUME_PACIENT, P.PRENUME_PACIENT,
    NVL(SUM(A.COST_ANALIZA), 0) AS COST_TOTAL_ANALIZE,
    NVL(SUM(T.COST_TRATAMENT), 0) AS COST_TOTAL_TRATAMENTE,
    NVL(SUM(C.COST_CONSULTATIE), 0) AS COST_TOTAL_CONSULTATIE,
    NVL(SUM(A.COST_ANALIZA), 0) + NVL(SUM(T.COST_TRATAMENT), 0) + NVL(SUM(C.COST_CONSULTATIE), 0) AS COST_TOTAL
    FROM PACIENT P
    LEFT JOIN CONSULTATIE C ON P.CNP_PACIENT = C.CNP_PACIENT
    LEFT JOIN ANALIZA A ON P.CNP_PACIENT = A.CNP_PACIENT
    LEFT JOIN DIAGNOSTIC D ON P.CNP_PACIENT = D.CNP_PACIENT
    LEFT JOIN TRATAMENT T ON D.ID_DIAGNOSTIC = T.ID_DIAGNOSTIC
    GROUP BY P.CNP_PACIENT, P.NUME_PACIENT, P.PRENUME_PACIENT)"""
    cursor = connection.cursor()
    cursor.execute(viz_complexa)
    cursor.execute("SELECT * FROM COST_TOTAL_PACIENT")
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    cursor.close()
    return render_template("viz_complexa.html", rows=rows, columns=columns)

if __name__ == "__main__":
    app.run(debug=True)