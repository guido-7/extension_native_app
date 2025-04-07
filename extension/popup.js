document.getElementById("send-button").addEventListener("click", () => {
    const messageDiv = document.getElementById("message");

    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
        const url = tabs[0].url;
        console.log("URL letto: ", url);

        const decodedPath = decodeURIComponent(url);
        console.log("Path decodificato:", decodedPath);

        const windowsPath = decodedPath.replace("file:///", "").replace(/\//g, "\\");
        console.log("Path Windows:", windowsPath);

        const name = document.getElementById("bookmark-name").value.trim();
        const page = parseInt(document.getElementById("bookmark-page").value);

        if (!name || isNaN(page) || page < 1) {
            showError("Inserisci titolo e pagina validi.");
            return;
        }

        const message = {
            action: "add_bookmark",
            file_directory: windowsPath,
            params: {
                bookmark_name: name,
                page: page
            }
        };

        console.log("Invio messaggio:", JSON.stringify(message));

        chrome.runtime.sendNativeMessage('com.guido.bookmarker', message, function (response) {
            if (chrome.runtime.lastError) {
                console.error("Errore Native Messaging:", chrome.runtime.lastError.message);
                messageDiv.style.color = "red";
                messageDiv.textContent = "Errore: " + chrome.runtime.lastError.message;
            } else {
                if (response.status === "success") {
                    messageDiv.style.color = "green";
                    messageDiv.textContent = "Successo: " + response.message + (response.output_file ? `. File generato: ${response.output_file}` : "");
                } else {
                    messageDiv.style.color = "red";
                    messageDiv.textContent = "Errore: " + response.message;
                }
            }
        });
    });

    function showError(text) {
        messageDiv.style.color = "red";
        messageDiv.textContent = text;
    }
});
