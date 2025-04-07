import sys
import json
import struct
import subprocess
import os # Utile per costruire percorsi

# --- Configurazione ---
# Assicurati che questo file esista davvero!
# Puoi usare os.path.join per creare percorsi in modo più sicuro
pdf_file_path = os.path.join(os.path.expanduser("~"), "Desktop", "03_Diodo.pdf")
# Verifica se il file esiste prima di eseguire il test
if not os.path.isfile(pdf_file_path):
    print(f"ERRORE: Il file PDF di test non esiste: {pdf_file_path}")
    sys.exit(1)

# Il messaggio da inviare (simula l'estensione)
message_to_send = {
    "file_directory": pdf_file_path,
    "action": "add_bookmark",
    "params": {
        "bookmark_name": "CIAO",
        "page": 1  # Ricorda: native_app.py dovrebbe convertirlo in indice 0 (cioè pagina 0)
    }
}

# Nome dello script dell'app nativa
native_app_script = 'native_app.py' # Assicurati che il percorso sia corretto

# Verifica se lo script nativo esiste
if not os.path.isfile(native_app_script):
    print(f"ERRORE: Lo script dell'app nativa non trovato: {native_app_script}")
    sys.exit(1)

print(f"Avvio di {native_app_script} per test...")
print(f"Invio messaggio: {json.dumps(message_to_send)}")

try:
    # Avvia l'app nativa come processo figlio
    proc = subprocess.Popen(
        ['python', native_app_script], # Assicurati che 'python' sia nel tuo PATH
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # Opzionale: specifica la directory di lavoro se necessario
        # cwd=...
    )

    # Codifica e invia il messaggio con il prefisso di lunghezza
    encoded_message = json.dumps(message_to_send).encode('utf-8')
    message_length = len(encoded_message)

    proc.stdin.write(struct.pack('@I', message_length)) # Usa @I per dimensione/ordine nativo standard
    proc.stdin.write(encoded_message)
    proc.stdin.flush()
    proc.stdin.close() # Segnala la fine dell'input

    # Leggi la risposta (lunghezza + messaggio) da stdout
    response_length_bytes = proc.stdout.read(4)
    if not response_length_bytes:
         print("ERRORE: Nessuna risposta ricevuta da stdout (l'app nativa potrebbe essere crashata?).")
         response_json = None
    else:
        response_length = struct.unpack('@I', response_length_bytes)[0]
        response_bytes = proc.stdout.read(response_length)
        response_str = response_bytes.decode('utf-8')
        print(f"\n>> Risposta ricevuta (raw): {response_str}")
        try:
            response_json = json.loads(response_str)
            print(f">> Risposta JSON: {response_json}")
        except json.JSONDecodeError:
            print("ERRORE: La risposta ricevuta non è JSON valido.")
            response_json = None

    # Leggi tutto l'output da stderr (i tuoi messaggi di debug)
    stderr_output = proc.stderr.read().decode('utf-8', errors='replace') # errors='replace' per evitare crash se ci sono caratteri strani
    print("\n>> Log di Debug (stderr):")
    print(stderr_output if stderr_output else "[Nessun output su stderr]")

    # Attendi la terminazione del processo e controlla il codice di uscita
    proc.wait(timeout=10) # Aggiungi un timeout per sicurezza
    print(f"\n>> Codice di uscita di {native_app_script}: {proc.returncode}")

    # Verifica il risultato del test (esempio)
    if proc.returncode == 0 and response_json and response_json.get("status") == "success":
        print("\n>> TEST PASSATO (App nativa terminata correttamente e risposta di successo ricevuta)")
        # Qui potresti anche controllare se il file _modified.pdf è stato creato
        modified_file = pdf_file_path.replace(".pdf", "_modified.pdf")
        if os.path.exists(modified_file):
            print(f">> File modificato trovato: {modified_file}")
        else:
            print(f">> ATTENZIONE: File modificato NON trovato: {modified_file}")

    else:
        print("\n>> TEST FALLITO (Controlla il codice di uscita e i log sopra)")

except FileNotFoundError:
     print(f"ERRORE: Impossibile eseguire 'python'. Assicurati che sia nel tuo PATH.")
except subprocess.TimeoutExpired:
    print("ERRORE: Timeout scaduto attendendo la fine dell'app nativa.")
    proc.kill() # Termina forzatamente il processo
    stdout, stderr = proc.communicate() # Leggi eventuali output rimanenti
    print(">> Ultimo stdout:", stdout.decode('utf-8', errors='replace'))
    print(">> Ultimo stderr:", stderr.decode('utf-8', errors='replace'))
except Exception as e:
    print(f"\nERRORE durante l'esecuzione del test: {e}")

finally:
    # Assicurati che gli stream siano chiusi anche in caso di errore
    if 'proc' in locals() and proc.stdin:
        proc.stdin.close()
    if 'proc' in locals() and proc.stdout:
        proc.stdout.close()
    if 'proc' in locals() and proc.stderr:
        proc.stderr.close()