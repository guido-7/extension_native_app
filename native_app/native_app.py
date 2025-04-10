#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import json
import struct
import os
import logging
from pypdf import PdfReader, PdfWriter  # Importa da pypdf
from pypdf.errors import PdfReadError
from pypdf.generic import Destination, Fit

# --- Configurazione del Logging ---
# Crea un file di log nella directory home dell'utente per un accesso facile
log_file_path = os.path.join(os.path.expanduser("~"), "edge_pdf_native_app.log")
logging.basicConfig(
    level=logging.DEBUG,  # Livello minimo di log da registrare (DEBUG è il più verboso)
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    filename=log_file_path,
    filemode='a',  # 'a' per append (aggiungere al file esistente), 'w' per sovrascrivere
    encoding='utf-8'
)
# --- Fine Configurazione ---


def read_message():
    """Legge un messaggio dal browser via stdin secondo il protocollo Native Messaging."""
    try:
        # Leggi i primi 4 byte che indicano la lunghezza del messaggio
        raw_length = sys.stdin.buffer.read(4)
        if not raw_length:
            logging.warning("Nessuna lunghezza letta da stdin (stream chiuso?). Uscita.")
            sys.exit(0)  # Uscita pulita se lo stream è chiuso

        # Interpreta i 4 byte come un intero unsigned nativo standard
        message_length = struct.unpack('@I', raw_length)[0]
        logging.debug(f"Lunghezza messaggio da leggere: {message_length}")

        # Limite di sicurezza per la dimensione del messaggio (es. 1MB)
        MAX_MESSAGE_LENGTH = 1 * 1024 * 1024
        if message_length > MAX_MESSAGE_LENGTH:
            logging.error(f"Lunghezza messaggio ({message_length}) supera il limite ({MAX_MESSAGE_LENGTH}). Uscita per sicurezza.")
            # Non possiamo inviare risposta se l'input è potenzialmente malizioso
            sys.exit(1)

        # Leggi il corpo del messaggio
        message_bytes = sys.stdin.buffer.read(message_length)
        if len(message_bytes) != message_length:
             logging.error(f"Errore lettura messaggio: letti {len(message_bytes)} bytes, attesi {message_length}.")
             sys.exit(1)

        # Decodifica il messaggio come UTF-8 e poi deserializza JSON
        message_str = message_bytes.decode('utf-8')
        logging.debug(f"Messaggio grezzo ricevuto: {message_str}")
        return json.loads(message_str)

    except struct.error as e:
        logging.exception(f"Errore unpack lunghezza messaggio: {e}")
        sys.exit(1)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logging.exception(f"Errore decodifica messaggio (JSON/UTF-8): {e}")
        sys.exit(1)
    except Exception as e:
        logging.exception(f"Errore imprevisto durante la lettura del messaggio: {e}")
        sys.exit(1)


def send_message(message_dict):
    """Invia un messaggio al browser via stdout secondo il protocollo Native Messaging."""
    try:
        message_str = json.dumps(message_dict)
        message_bytes = message_str.encode('utf-8')
        message_length = len(message_bytes)

        logging.debug(f"Invio messaggio di lunghezza: {message_length}")
        # Scrivi la lunghezza (4 byte, intero unsigned nativo standard)
        sys.stdout.buffer.write(struct.pack('@I', message_length))
        # Scrivi il corpo del messaggio
        sys.stdout.buffer.write(message_bytes)
        # Assicura che il messaggio sia inviato immediatamente
        sys.stdout.buffer.flush()
        logging.debug(f"Risposta inviata: {message_str}")

    except Exception as e:
        # Se l'invio fallisce, possiamo solo loggare l'errore.
        logging.exception(f"Errore durante l'invio del messaggio a stdout: {e}")
        # Potrebbe essere che il browser abbia chiuso la connessione.


def file_is_pdf(path):
    """Verifica base se il percorso è un file e finisce con .pdf (case-insensitive)."""
    is_pdf = os.path.isfile(path) and path.lower().endswith(".pdf")
    logging.debug(f"Verifica se è un file PDF valido: '{path}' -> {is_pdf}")
    return is_pdf


# Nota: La gestione degli outline esistenti in pypdf è un po' diversa
# Questa funzione è semplificata e potrebbe non rilevare tutti i bookmark esistenti
# su una pagina se sono nidificati in modo complesso.
def bookmark_exists_on_page(reader: PdfReader, page_zero_indexed: int) -> bool:
    """Verifica semplificata se esiste già un bookmark che punta alla pagina specificata."""
    try:
        for item in reader.outline:
            # reader.get_destination_page_number(item) può essere complesso
            # Usiamo un controllo più diretto se disponibile o logghiamo se non riusciamo
            try:
                # Il modo diretto per ottenere la pagina da un item outline può variare
                # Controlliamo se l'item punta direttamente a una pagina
                page_index = reader.get_page_number(item.page) # Tentativo, potrebbe non funzionare per tutti i tipi di destinazione
                if page_index == page_zero_indexed:
                    logging.debug(f"Trovato bookmark esistente per pagina indice {page_zero_indexed}")
                    return True
            except Exception:
                 # Ignora item che non puntano direttamente a pagine o causano errori
                 pass
            # Potremmo dover navigare ricorsivamente negli item nidificati,
            # ma per ora manteniamo semplice.
    except Exception as e:
        logging.warning(f"Errore durante la verifica dei bookmark esistenti: {e}")
    return False

def create_structure(reader, outlines, title, page_index, parent=None, ):
    if parent is None:
        page_obj = reader.pages[page_index]
        new_outline = Destination(title=title, page=page_obj , fit=Fit(fit_type="/Fit"))
        outlines.append(new_outline)

        def get_page_number(dest):
            try:
                return reader.get_page_number(dest.page)
            except Exception:
                return float("inf")  # Se non si riesce, lo mettiamo in fondo

        # Ordina la lista principale mantenendo l’ordine originale dei nidificati
        outlines.sort(key=lambda d: get_page_number(d) if isinstance(d, Destination) else float("inf"))
        return outlines
    return None

def insert_bookmark(reader: PdfReader, writer: PdfWriter, item, parent=None):
    """Copia un bookmark esistente in un nuovo writer."""
    if isinstance(item, list):
        # Se l'item è una lista, è un bookmark nidificato
        for sub_item in item:
            insert_bookmark(reader, writer, sub_item, parent)
    elif isinstance(item, dict):
        # Se l'item è un dizionario, è un bookmark semplice
        page_index = reader.get_page_number(item.page)  # Potrebbe non funzionare per tutti i tipi di destinazione
        writer.add_outline_item(title=item.title, page_number=page_index, parent=parent)

def add_bookmark_to_pdf(pdf_path, bookmark_title, page_zero_indexed):
    """Aggiunge un bookmark a un file PDF usando pypdf."""
    output_path_final = pdf_path
    output_path_temp = pdf_path.replace(".pdf", "_temp.pdf")

    try:
        logging.info(f"Tentativo di aggiungere bookmark '{bookmark_title}' a pagina indice {page_zero_indexed} del file: {pdf_path}")

        # Verifica esistenza file sorgente
        if not os.path.isfile(pdf_path):
            logging.error(f"File PDF sorgente non trovato: {pdf_path}")
            return False, f"File non trovato: {pdf_path}"

        # Apre il PDF esistente
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        # Verifica validità numero di pagina
        num_pages = len(reader.pages)
        if not (0 <= page_zero_indexed < num_pages):
            msg = f"Numero pagina {page_zero_indexed + 1} non valido. Il PDF ha {num_pages} pagine (da 1 a {num_pages})."
            logging.error(msg)
            return False, msg

        # Clona tutte le pagine dal reader al writer
        # writer.clone_document_from_reader(reader) # Metodo più moderno se si vogliono copiare anche metadati/outline
        for page in reader.pages:
             writer.add_page(page)

        # Copia i metadati se presenti
        metadata = reader.metadata
        if metadata:
            writer.add_metadata(metadata)

        # Verifica (semplificata) se esiste già un bookmark sulla pagina
        # if bookmark_exists_on_page(reader, page_zero_indexed):
        #     msg = f"Esiste già un bookmark per la pagina {page_zero_indexed + 1}."
        #     logging.warning(msg)
        #     # Decidi se questo è un errore o solo un avviso
        #     # return False, msg # Scommenta per bloccare se esiste già

        outlines = create_structure(reader, reader.outline, bookmark_title, page_zero_indexed)

        # Inserisce gli outline nel nuovo pdf
        insert_bookmark(reader=reader, writer=writer, item=outlines)

        # Aggiunge il nuovo bookmark (outline item)
        logging.debug(f"Aggiungo bookmark '{bookmark_title}' a pagina indice {page_zero_indexed}")
        # Il metodo add_outline_item è quello corretto in pypdf > 2.11
        #writer.add_outline_item(title=bookmark_title, page_number=page_zero_indexed, parent=None)

        # Scrive il PDF modificato su un file temporaneo
        logging.debug(f"Scrivo modifiche su file temporaneo: {output_path_temp}")
        with open(output_path_temp, "wb") as out_f:
            writer.write(out_f)

        # Se la scrittura temporanea ha successo, sostituisce il vecchio file modificato (se esiste)
        # o rinomina il file temporaneo nel nome finale.
        logging.debug(f"Rinomino {output_path_temp} in {output_path_final}")
        if os.path.exists(output_path_final):
            os.remove(output_path_final)
        os.rename(output_path_temp, output_path_final)

        logging.info(f"Bookmark aggiunto con successo. PDF modificato salvato in: {output_path_final}")
        return True, output_path_final

    except PdfReadError as e:
        logging.exception(f"Errore lettura PDF (file corrotto o protetto?): {pdf_path} - {e}")
        return False, f"Errore durante la lettura del PDF: {e}. Il file potrebbe essere corrotto o protetto da password."
    except Exception as e:
        logging.exception(f"Errore imprevisto durante l'aggiunta del bookmark: {e}")
        # Prova a pulire il file temporaneo se esiste
        if os.path.exists(output_path_temp):
            try:
                os.remove(output_path_temp)
            except OSError:
                logging.warning(f"Impossibile rimuovere il file temporaneo: {output_path_temp}")
        return False, f"Errore interno durante la modifica del PDF: {e}"


def process_message(message):
    """Elabora il messaggio ricevuto e determina l'azione da intraprendere."""
    file_directory = message.get("file_directory")
    action = message.get("action")
    params = message.get("params", {})

    logging.info(f"Ricevuta richiesta: Azione='{action}', File='{file_directory}', Parametri='{params}'")

    # Validazione input base
    if not file_directory or not action:
        logging.error("Richiesta invalida: 'file_directory' o 'action' mancanti.")
        return {"status": "error", "message": "Parametri 'file_directory' e 'action' mancanti nella richiesta."}

    if not isinstance(file_directory, str) or not isinstance(action, str):
         logging.error("Richiesta invalida: 'file_directory' o 'action' non sono stringhe.")
         return {"status": "error", "message": "'file_directory' e 'action' devono essere stringhe."}

    if not file_is_pdf(file_directory):
        logging.error(f"Il percorso fornito non è un file PDF valido: {file_directory}")
        return {"status": "error", "message": "Il percorso fornito non è un file o non ha estensione .pdf."}

    # Gestione Azioni
    if action == "add_bookmark":
        bookmark_name = params.get("bookmark_name")
        page_one_based = params.get("page") # Numero di pagina dall'utente (1-based)

        if bookmark_name is None or page_one_based is None:
            logging.error("Parametri mancanti per 'add_bookmark': 'bookmark_name' o 'page'.")
            return {"status": "error", "message": "Parametri 'bookmark_name' e 'page' necessari per aggiungere un bookmark."}

        if not isinstance(bookmark_name, str) or not bookmark_name.strip():
             logging.error(f"Nome bookmark non valido: '{bookmark_name}'")
             return {"status": "error", "message": "Il nome del bookmark non può essere vuoto."}

        try:
            # Converte la pagina in intero (dall'utente, 1-based)
            page_one_based_int = int(page_one_based)
            if page_one_based_int < 1:
                 logging.error(f"Numero pagina non valido: {page_one_based_int}. Deve essere >= 1.")
                 return {"status": "error", "message": f"Numero pagina non valido: {page_one_based_int}. Deve essere 1 o maggiore."}
            # Converte in indice 0-based per pypdf
            page_zero_indexed = page_one_based_int - 1
        except (ValueError, TypeError):
            logging.error(f"Numero pagina non valido: '{page_one_based}'. Deve essere un intero.")
            return {"status": "error", "message": f"Il numero di pagina fornito ('{page_one_based}') non è un numero intero valido."}

        # Chiama la funzione per aggiungere il bookmark
        success, result = add_bookmark_to_pdf(file_directory, bookmark_name.strip(), page_zero_indexed)

        if success:
            logging.info("Azione 'add_bookmark' completata con successo.")
            return {"status": "success", "message": "Bookmark aggiunto con successo.", "output_file": result}
        else:
            logging.error(f"Azione 'add_bookmark' fallita: {result}")
            return {"status": "error", "message": result} # 'result' contiene il messaggio di errore

    else:
        logging.warning(f"Azione non supportata richiesta: '{action}'")
        return {"status": "error", "message": f"Azione '{action}' non supportata."}


# --- Blocco Principale di Esecuzione ---
if __name__ == '__main__':
    logging.info("--- Avvio Native App PDF ---")
    try:
        # Leggi un singolo messaggio da stdin
        received_message = read_message()

        if received_message:
            # Elabora il messaggio
            response_message = process_message(received_message)
            # Invia la risposta a stdout
            send_message(response_message)
            logging.info("Elaborazione completata, risposta inviata.")
        else:
             # read_message ha già loggato l'errore o l'uscita pulita
             logging.warning("Nessun messaggio valido ricevuto o stream chiuso.")

    except Exception as e:
        # Cattura eccezioni impreviste nel flusso principale
        logging.exception("Errore critico non gestito nel blocco main!")
        # Prova a inviare un messaggio di errore generico se possibile
        try:
            error_response = {
                "status": "error",
                "message": f"Errore interno critico nell'applicazione nativa: {e}"
            }
            send_message(error_response)
        except Exception as send_e:
            logging.error(f"Impossibile inviare messaggio di errore critico al browser: {send_e}")

    finally:
        logging.info("--- Chiusura Native App PDF ---")
        logging.shutdown() # Assicura che tutti i log siano scritti prima di uscire