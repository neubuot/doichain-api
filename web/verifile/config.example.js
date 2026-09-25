// Konfiguration der Verifile-App. install.sh erzeugt auf dem Server die echte config.js mit dem poe-Schluessel
// aus /etc/doichain-api/doichain-api.env (DOI_API_KEYS_POE). Der Schluessel ist im Browser sichtbar und darf
// deshalb nur Nachweise anlegen, mit Tageskontingent je IP-Adresse und insgesamt.
window.VERIFILE_CONFIG = {
  apiBase: "https://doi-api.sendlabs.de",
  poeKey: "",
  explorer: "https://doi-explorer.le-space.de",
};
