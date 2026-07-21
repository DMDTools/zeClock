// zeClock Web UI - Internationalization (i18n)
// Supported languages: en, fr, de, es

const translations = {
    en: {
        // Header
        "header.title": "🕒 zeClock",
        "header.download_settings": "Download settings backup",
        "header.upload_settings": "Upload settings backup",

        // Tabs
        "tab.dashboard": "Dashboard",
        "tab.speaker_timer": "Speaker Timer",
        "tab.message": "Message",
        "tab.settings": "⚙️ Settings",

        // Backend banner
        "banner.waiting": "Waiting for ZeDMD display connection...",

        // Dashboard
        "dashboard.screen": "Screen",
        "dashboard.screen_on": "Screen ON",
        "dashboard.screen_off": "Screen OFF",
        "dashboard.brightness": "Brightness",
        "dashboard.brightness_set": "Set",
        "dashboard.brightness_auto": "Auto",
        "dashboard.brightness_mode_auto": "Mode: auto",
        "dashboard.plugins": "Plugins",
        "dashboard.plugins_loading": "Loading...",
        "dashboard.plugins_none": "No plugins available",
        "dashboard.plugins_resume": "Resume Rotation",
        "dashboard.status": "Status",
        "dashboard.status_loading": "Loading...",

        // Speaker Timer
        "timer.idle": "IDLE",
        "timer.start": "▶ Start",
        "timer.pause": "⏸ Pause",
        "timer.reset": "⏹ Reset",
        "timer.presets": "Presets",
        "timer.custom_duration": "Custom Duration",
        "timer.set": "Set",
        "timer.message_to_speaker": "Message to Speaker",
        "timer.message_placeholder": "Message to speaker...",
        "timer.send": "Send",
        "timer.quick_wrap_up": "Wrap up",
        "timer.quick_louder": "Speak louder",
        "timer.quick_qa": "Q&A 5 min",
        "timer.quick_thanks": "Thank you!",
        "timer.quick_slow_down": "Slow down",

        // Message
        "message.title": "Send Message to Display",
        "message.description": "Display a message on the clock for a set duration. Useful for sending discreet messages to a speaker.",
        "message.placeholder": "Your message...",
        "message.duration_label": "Duration (seconds):",
        "message.send": "Send Message",
        "message.quick_title": "Quick Messages",
        "message.quick_wrap_up": "Wrap up",
        "message.quick_louder": "Speak louder",
        "message.quick_qa": "Q&A 5 min",
        "message.quick_thanks": "Thank you!",

        // Settings
        "settings.general": "General",
        "settings.hardware": "🖥️ Hardware",
        "settings.connectivity": "🔌 Connectivity",
        "settings.zedmd_backend": "ZeDMD Backend",
        "settings.wifi_addr": "ZeDMD WiFi Address",
        "settings.default_brightness": "Default Brightness (0-15)",
        "settings.display": "Display",
        "settings.font": "Font",
        "settings.location": "Location",
        "settings.location_search": "Search city or address",
        "settings.location_search_placeholder": "Start typing a city or address...",
        "settings.latitude": "Latitude",
        "settings.longitude": "Longitude",
        "settings.city_name": "City Name",
        "settings.location_hint": "Coordinates and city name are auto-filled when you select a location above.",
        "settings.brightness_schedule": "Brightness Schedule",
        "settings.max_brightness": "Max Brightness (0-15)",
        "settings.schedule_default": "Default Schedule (e.g. 22:00-08:00 20%)",
        "settings.sunrise_brightness": "Sunrise Brightness %",
        "settings.sunset_brightness": "Sunset Brightness %",
        "settings.rest_api": "REST API",
        "settings.rest_enabled": "Enabled",
        "settings.rest_port": "Port",
        "settings.plugins": "Plugins",
        "settings.language": "Language",
        "settings.language_desc": "Language for the interface and all plugins (day names, weather, etc.)",
        "settings.default_plugin": "Default Plugin (displayed between rotations)",
        "settings.default_plugin_desc": "The plugin displayed between each rotation plugin (e.g. the clock between weather, pinball, etc.)",
        "settings.display_duration": "Display Duration (seconds between rotations)",
        "settings.add_plugin": "+ Add Plugin",
        "settings.plugin_config": "🔧 Plugin Configuration",
        "settings.plugin_name": "Plugin",
        "settings.plugin_weight": "Weight",
        "settings.plugin_weight_desc": "Higher weight = more likely to be selected. Set to 0 to disable a plugin.",
        "settings.plugin_remove": "Remove",

        // Connection status
        "status.connected": "Connected",
        "status.disconnected": "Disconnected",

        // Config status
        "config.saving": "⏳ Saving...",
        "config.saved": "✅ Saved",
        "config.error": "❌ Error: ",
        "config.save_failed": "❌ Save failed",

        // Alerts
        "alert.enter_message": "Please enter a message",
        "alert.export_failed": "Failed to export settings: ",
        "alert.invalid_file": "Invalid settings file: ",
        "alert.restore_confirm": "Restore settings from this backup?\nThis will overwrite your current configuration.",
        "alert.restore_success": "✅ Settings restored successfully. Reloading...",
        "alert.restore_failed": "❌ Failed to restore settings: ",

        // Boolean toggles
        "bool.yes": "Yes",
        "bool.no": "No",

        // GIF directories
        "gif.no_valid": "No valid GIF files selected",
        "gif.uploading": "Uploading {count} file(s)...",
        "gif.no_dirs": "No existing directories found. Upload some GIFs first!",
        "gif.new_dir_prompt": "Enter a name for the new GIF directory:",

        // Location
        "location.no_results": "No results found",

        // Misc
        "plugin.default_badge": "default",

        // Settings sidebar & theme
        "settings.cat_general": "General",
        "settings.cat_location": "Location",
        "settings.cat_hardware": "Hardware",
        "settings.cat_connectivity": "Connectivity",
        "settings.cat_plugins": "Plugins",
        "settings.cat_plugin_config": "Plugin Configuration",
        "settings.theme_toggle": "Toggle theme",
        "settings.theme_dark": "Dark",
        "settings.theme_light": "Light",
        "config.save_failed_final": "Save failed after retries. Change not applied.",
        "config.retry_failed": "Retry failed",
        "settings.backup_download": "Download Backup",
        "settings.backup_restore": "Restore Backup",
        "settings.file_too_large": "File too large (max 1MB)",
        "settings.invalid_json": "Invalid JSON file",
        "settings.cat_debug": "Debug",
        "settings.debug_system": "System Info",
        "settings.debug_logs": "Live Logs",
        "settings.debug_refresh": "Refresh",
    },

    fr: {
        // Header
        "header.title": "🕒 zeClock",
        "header.download_settings": "Télécharger la sauvegarde des paramètres",
        "header.upload_settings": "Importer une sauvegarde des paramètres",

        // Tabs
        "tab.dashboard": "Tableau de bord",
        "tab.speaker_timer": "Chrono orateur",
        "tab.message": "Message",
        "tab.settings": "⚙️ Paramètres",

        // Backend banner
        "banner.waiting": "En attente de connexion à l'écran ZeDMD...",

        // Dashboard
        "dashboard.screen": "Écran",
        "dashboard.screen_on": "Allumer",
        "dashboard.screen_off": "Éteindre",
        "dashboard.brightness": "Luminosité",
        "dashboard.brightness_set": "Appliquer",
        "dashboard.brightness_auto": "Auto",
        "dashboard.brightness_mode_auto": "Mode : auto",
        "dashboard.plugins": "Plugins",
        "dashboard.plugins_loading": "Chargement...",
        "dashboard.plugins_none": "Aucun plugin disponible",
        "dashboard.plugins_resume": "Reprendre la rotation",
        "dashboard.status": "État",
        "dashboard.status_loading": "Chargement...",

        // Speaker Timer
        "timer.idle": "INACTIF",
        "timer.start": "▶ Démarrer",
        "timer.pause": "⏸ Pause",
        "timer.reset": "⏹ Réinitialiser",
        "timer.presets": "Préréglages",
        "timer.custom_duration": "Durée personnalisée",
        "timer.set": "Définir",
        "timer.message_to_speaker": "Message à l'orateur",
        "timer.message_placeholder": "Message à l'orateur...",
        "timer.send": "Envoyer",
        "timer.quick_wrap_up": "Conclure",
        "timer.quick_louder": "Plus fort",
        "timer.quick_qa": "Q&R 5 min",
        "timer.quick_thanks": "Merci !",
        "timer.quick_slow_down": "Ralentir",

        // Message
        "message.title": "Envoyer un message à l'écran",
        "message.description": "Affiche un message sur l'horloge pendant une durée définie. Utile pour envoyer des messages discrets à un orateur.",
        "message.placeholder": "Votre message...",
        "message.duration_label": "Durée (secondes) :",
        "message.send": "Envoyer",
        "message.quick_title": "Messages rapides",
        "message.quick_wrap_up": "Conclure",
        "message.quick_louder": "Plus fort",
        "message.quick_qa": "Q&R 5 min",
        "message.quick_thanks": "Merci !",

        // Settings
        "settings.general": "Général",
        "settings.hardware": "🖥️ Matériel",
        "settings.connectivity": "🔌 Connectivité",
        "settings.zedmd_backend": "Backend ZeDMD",
        "settings.wifi_addr": "Adresse WiFi ZeDMD",
        "settings.default_brightness": "Luminosité par défaut (0-15)",
        "settings.display": "Affichage",
        "settings.font": "Police",
        "settings.location": "Localisation",
        "settings.location_search": "Rechercher une ville ou adresse",
        "settings.location_search_placeholder": "Commencez à taper une ville ou adresse...",
        "settings.latitude": "Latitude",
        "settings.longitude": "Longitude",
        "settings.city_name": "Nom de la ville",
        "settings.location_hint": "Les coordonnées et le nom de la ville sont remplis automatiquement lorsque vous sélectionnez un lieu ci-dessus.",
        "settings.brightness_schedule": "Planification luminosité",
        "settings.max_brightness": "Luminosité max (0-15)",
        "settings.schedule_default": "Plage par défaut (ex. 22:00-08:00 20%)",
        "settings.sunrise_brightness": "Luminosité lever du soleil %",
        "settings.sunset_brightness": "Luminosité coucher du soleil %",
        "settings.rest_api": "API REST",
        "settings.rest_enabled": "Activée",
        "settings.rest_port": "Port",
        "settings.plugins": "Plugins",
        "settings.language": "Langue",
        "settings.language_desc": "Langue de l'interface et de tous les plugins (noms des jours, météo, etc.)",
        "settings.default_plugin": "Plugin par défaut (affiché entre les rotations)",
        "settings.default_plugin_desc": "Le plugin affiché entre chaque rotation (ex. l'horloge entre météo, flipper, etc.)",
        "settings.display_duration": "Durée d'affichage (secondes entre rotations)",
        "settings.add_plugin": "+ Ajouter un plugin",
        "settings.plugin_config": "🔧 Configuration des plugins",
        "settings.plugin_name": "Plugin",
        "settings.plugin_weight": "Poids",
        "settings.plugin_weight_desc": "Plus le poids est élevé, plus le plugin sera sélectionné souvent. Mettre à 0 pour désactiver.",
        "settings.plugin_remove": "Supprimer",

        // Connection status
        "status.connected": "Connecté",
        "status.disconnected": "Déconnecté",

        // Config status
        "config.saving": "⏳ Enregistrement...",
        "config.saved": "✅ Enregistré",
        "config.error": "❌ Erreur : ",
        "config.save_failed": "❌ Échec de la sauvegarde",

        // Alerts
        "alert.enter_message": "Veuillez entrer un message",
        "alert.export_failed": "Échec de l'export des paramètres : ",
        "alert.invalid_file": "Fichier de paramètres invalide : ",
        "alert.restore_confirm": "Restaurer les paramètres depuis cette sauvegarde ?\nCela écrasera votre configuration actuelle.",
        "alert.restore_success": "✅ Paramètres restaurés avec succès. Rechargement...",
        "alert.restore_failed": "❌ Échec de la restauration : ",

        // Boolean toggles
        "bool.yes": "Oui",
        "bool.no": "Non",

        // GIF directories
        "gif.no_valid": "Aucun fichier GIF valide sélectionné",
        "gif.uploading": "Envoi de {count} fichier(s)...",
        "gif.no_dirs": "Aucun répertoire trouvé. Envoyez d'abord des GIFs !",
        "gif.new_dir_prompt": "Nom du nouveau répertoire de GIFs :",

        // Location
        "location.no_results": "Aucun résultat",

        // Misc
        "plugin.default_badge": "défaut",

        // Settings sidebar & theme
        "settings.cat_general": "Général",
        "settings.cat_location": "Localisation",
        "settings.cat_hardware": "Matériel",
        "settings.cat_connectivity": "Connectivité",
        "settings.cat_plugins": "Plugins",
        "settings.cat_plugin_config": "Configuration des plugins",
        "settings.theme_toggle": "Basculer le thème",
        "settings.theme_dark": "Sombre",
        "settings.theme_light": "Clair",
        "config.save_failed_final": "Échec de la sauvegarde après plusieurs tentatives. Modification non appliquée.",
        "config.retry_failed": "Nouvelle tentative échouée",
        "settings.backup_download": "Télécharger la sauvegarde",
        "settings.backup_restore": "Restaurer la sauvegarde",
        "settings.file_too_large": "Fichier trop volumineux (max 1 Mo)",
        "settings.invalid_json": "Fichier JSON invalide",
        "settings.cat_debug": "Debug",
        "settings.debug_system": "Infos système",
        "settings.debug_logs": "Logs en direct",
        "settings.debug_refresh": "Rafraîchir",
    },

    de: {
        // Header
        "header.title": "🕒 zeClock",
        "header.download_settings": "Einstellungen herunterladen",
        "header.upload_settings": "Einstellungen hochladen",

        // Tabs
        "tab.dashboard": "Übersicht",
        "tab.speaker_timer": "Redner-Timer",
        "tab.message": "Nachricht",
        "tab.settings": "⚙️ Einstellungen",

        // Backend banner
        "banner.waiting": "Warte auf ZeDMD-Display-Verbindung...",

        // Dashboard
        "dashboard.screen": "Bildschirm",
        "dashboard.screen_on": "Einschalten",
        "dashboard.screen_off": "Ausschalten",
        "dashboard.brightness": "Helligkeit",
        "dashboard.brightness_set": "Setzen",
        "dashboard.brightness_auto": "Auto",
        "dashboard.brightness_mode_auto": "Modus: auto",
        "dashboard.plugins": "Plugins",
        "dashboard.plugins_loading": "Laden...",
        "dashboard.plugins_none": "Keine Plugins verfügbar",
        "dashboard.plugins_resume": "Rotation fortsetzen",
        "dashboard.status": "Status",
        "dashboard.status_loading": "Laden...",

        // Speaker Timer
        "timer.idle": "BEREIT",
        "timer.start": "▶ Start",
        "timer.pause": "⏸ Pause",
        "timer.reset": "⏹ Zurücksetzen",
        "timer.presets": "Voreinstellungen",
        "timer.custom_duration": "Eigene Dauer",
        "timer.set": "Setzen",
        "timer.message_to_speaker": "Nachricht an Redner",
        "timer.message_placeholder": "Nachricht an Redner...",
        "timer.send": "Senden",
        "timer.quick_wrap_up": "Abschließen",
        "timer.quick_louder": "Lauter sprechen",
        "timer.quick_qa": "Q&A 5 Min",
        "timer.quick_thanks": "Danke!",
        "timer.quick_slow_down": "Langsamer",

        // Message
        "message.title": "Nachricht ans Display senden",
        "message.description": "Zeigt eine Nachricht auf der Uhr für eine bestimmte Dauer an. Nützlich für diskrete Nachrichten an einen Redner.",
        "message.placeholder": "Ihre Nachricht...",
        "message.duration_label": "Dauer (Sekunden):",
        "message.send": "Senden",
        "message.quick_title": "Schnellnachrichten",
        "message.quick_wrap_up": "Abschließen",
        "message.quick_louder": "Lauter sprechen",
        "message.quick_qa": "Q&A 5 Min",
        "message.quick_thanks": "Danke!",

        // Settings
        "settings.general": "Allgemein",
        "settings.hardware": "🖥️ Hardware",
        "settings.connectivity": "🔌 Konnektivität",
        "settings.zedmd_backend": "ZeDMD-Backend",
        "settings.wifi_addr": "ZeDMD WiFi-Adresse",
        "settings.default_brightness": "Standard-Helligkeit (0-15)",
        "settings.display": "Anzeige",
        "settings.font": "Schriftart",
        "settings.location": "Standort",
        "settings.location_search": "Stadt oder Adresse suchen",
        "settings.location_search_placeholder": "Stadt oder Adresse eingeben...",
        "settings.latitude": "Breitengrad",
        "settings.longitude": "Längengrad",
        "settings.city_name": "Stadtname",
        "settings.location_hint": "Koordinaten und Stadtname werden automatisch ausgefüllt, wenn Sie oben einen Ort auswählen.",
        "settings.brightness_schedule": "Helligkeitsplan",
        "settings.max_brightness": "Max. Helligkeit (0-15)",
        "settings.schedule_default": "Standardplan (z.B. 22:00-08:00 20%)",
        "settings.sunrise_brightness": "Helligkeit Sonnenaufgang %",
        "settings.sunset_brightness": "Helligkeit Sonnenuntergang %",
        "settings.rest_api": "REST-API",
        "settings.rest_enabled": "Aktiviert",
        "settings.rest_port": "Port",
        "settings.plugins": "Plugins",
        "settings.language": "Sprache",
        "settings.language_desc": "Sprache für die Oberfläche und alle Plugins (Tagesnamen, Wetter, usw.)",
        "settings.default_plugin": "Standard-Plugin (zwischen Rotationen)",
        "settings.default_plugin_desc": "Das Plugin, das zwischen Rotationen angezeigt wird (z.B. Uhr zwischen Wetter, Flipper, usw.)",
        "settings.display_duration": "Anzeigedauer (Sekunden zwischen Rotationen)",
        "settings.add_plugin": "+ Plugin hinzufügen",
        "settings.plugin_config": "🔧 Plugin-Konfiguration",
        "settings.plugin_name": "Plugin",
        "settings.plugin_weight": "Gewicht",
        "settings.plugin_weight_desc": "Höheres Gewicht = häufiger ausgewählt. Auf 0 setzen um ein Plugin zu deaktivieren.",
        "settings.plugin_remove": "Entfernen",

        // Connection status
        "status.connected": "Verbunden",
        "status.disconnected": "Getrennt",

        // Config status
        "config.saving": "⏳ Speichern...",
        "config.saved": "✅ Gespeichert",
        "config.error": "❌ Fehler: ",
        "config.save_failed": "❌ Speichern fehlgeschlagen",

        // Alerts
        "alert.enter_message": "Bitte geben Sie eine Nachricht ein",
        "alert.export_failed": "Export fehlgeschlagen: ",
        "alert.invalid_file": "Ungültige Einstellungsdatei: ",
        "alert.restore_confirm": "Einstellungen aus diesem Backup wiederherstellen?\nDies überschreibt Ihre aktuelle Konfiguration.",
        "alert.restore_success": "✅ Einstellungen erfolgreich wiederhergestellt. Neuladen...",
        "alert.restore_failed": "❌ Wiederherstellung fehlgeschlagen: ",

        // Boolean toggles
        "bool.yes": "Ja",
        "bool.no": "Nein",

        // GIF directories
        "gif.no_valid": "Keine gültigen GIF-Dateien ausgewählt",
        "gif.uploading": "{count} Datei(en) werden hochgeladen...",
        "gif.no_dirs": "Keine Verzeichnisse gefunden. Laden Sie zuerst GIFs hoch!",
        "gif.new_dir_prompt": "Name des neuen GIF-Verzeichnisses:",

        // Location
        "location.no_results": "Keine Ergebnisse",

        // Misc
        "plugin.default_badge": "Standard",

        // Settings sidebar & theme
        "settings.cat_general": "Allgemein",
        "settings.cat_location": "Standort",
        "settings.cat_hardware": "Hardware",
        "settings.cat_connectivity": "Konnektivität",
        "settings.cat_plugins": "Plugins",
        "settings.cat_plugin_config": "Plugin-Konfiguration",
        "settings.theme_toggle": "Design umschalten",
        "settings.theme_dark": "Dunkel",
        "settings.theme_light": "Hell",
        "config.save_failed_final": "Speichern nach Wiederholungen fehlgeschlagen. Änderung nicht übernommen.",
        "config.retry_failed": "Wiederholung fehlgeschlagen",
        "settings.backup_download": "Sicherung herunterladen",
        "settings.backup_restore": "Sicherung wiederherstellen",
        "settings.file_too_large": "Datei zu groß (max. 1 MB)",
        "settings.invalid_json": "Ungültige JSON-Datei",
        "settings.cat_debug": "Debug",
        "settings.debug_system": "Systeminfo",
        "settings.debug_logs": "Live-Logs",
        "settings.debug_refresh": "Aktualisieren",
    },

    es: {
        // Header
        "header.title": "🕒 zeClock",
        "header.download_settings": "Descargar copia de seguridad",
        "header.upload_settings": "Importar copia de seguridad",

        // Tabs
        "tab.dashboard": "Panel",
        "tab.speaker_timer": "Cronómetro",
        "tab.message": "Mensaje",
        "tab.settings": "⚙️ Ajustes",

        // Backend banner
        "banner.waiting": "Esperando conexión con la pantalla ZeDMD...",

        // Dashboard
        "dashboard.screen": "Pantalla",
        "dashboard.screen_on": "Encender",
        "dashboard.screen_off": "Apagar",
        "dashboard.brightness": "Brillo",
        "dashboard.brightness_set": "Aplicar",
        "dashboard.brightness_auto": "Auto",
        "dashboard.brightness_mode_auto": "Modo: auto",
        "dashboard.plugins": "Plugins",
        "dashboard.plugins_loading": "Cargando...",
        "dashboard.plugins_none": "No hay plugins disponibles",
        "dashboard.plugins_resume": "Reanudar rotación",
        "dashboard.status": "Estado",
        "dashboard.status_loading": "Cargando...",

        // Speaker Timer
        "timer.idle": "INACTIVO",
        "timer.start": "▶ Iniciar",
        "timer.pause": "⏸ Pausa",
        "timer.reset": "⏹ Reiniciar",
        "timer.presets": "Preajustes",
        "timer.custom_duration": "Duración personalizada",
        "timer.set": "Establecer",
        "timer.message_to_speaker": "Mensaje al orador",
        "timer.message_placeholder": "Mensaje al orador...",
        "timer.send": "Enviar",
        "timer.quick_wrap_up": "Terminar",
        "timer.quick_louder": "Más fuerte",
        "timer.quick_qa": "Q&A 5 min",
        "timer.quick_thanks": "¡Gracias!",
        "timer.quick_slow_down": "Más lento",

        // Message
        "message.title": "Enviar mensaje a la pantalla",
        "message.description": "Muestra un mensaje en el reloj durante un tiempo determinado. Útil para enviar mensajes discretos a un orador.",
        "message.placeholder": "Su mensaje...",
        "message.duration_label": "Duración (segundos):",
        "message.send": "Enviar mensaje",
        "message.quick_title": "Mensajes rápidos",
        "message.quick_wrap_up": "Terminar",
        "message.quick_louder": "Más fuerte",
        "message.quick_qa": "Q&A 5 min",
        "message.quick_thanks": "¡Gracias!",

        // Settings
        "settings.general": "General",
        "settings.hardware": "🖥️ Hardware",
        "settings.connectivity": "🔌 Conectividad",
        "settings.zedmd_backend": "Backend ZeDMD",
        "settings.wifi_addr": "Dirección WiFi ZeDMD",
        "settings.default_brightness": "Brillo predeterminado (0-15)",
        "settings.display": "Pantalla",
        "settings.font": "Fuente",
        "settings.location": "Ubicación",
        "settings.location_search": "Buscar ciudad o dirección",
        "settings.location_search_placeholder": "Escriba una ciudad o dirección...",
        "settings.latitude": "Latitud",
        "settings.longitude": "Longitud",
        "settings.city_name": "Nombre de la ciudad",
        "settings.location_hint": "Las coordenadas y el nombre de la ciudad se rellenan automáticamente al seleccionar una ubicación arriba.",
        "settings.brightness_schedule": "Programación de brillo",
        "settings.max_brightness": "Brillo máximo (0-15)",
        "settings.schedule_default": "Programación (ej. 22:00-08:00 20%)",
        "settings.sunrise_brightness": "Brillo amanecer %",
        "settings.sunset_brightness": "Brillo atardecer %",
        "settings.rest_api": "API REST",
        "settings.rest_enabled": "Activada",
        "settings.rest_port": "Puerto",
        "settings.plugins": "Plugins",
        "settings.language": "Idioma",
        "settings.language_desc": "Idioma de la interfaz y todos los plugins (nombres de días, clima, etc.)",
        "settings.default_plugin": "Plugin predeterminado (entre rotaciones)",
        "settings.default_plugin_desc": "El plugin que se muestra entre rotaciones (ej. reloj entre clima, pinball, etc.)",
        "settings.display_duration": "Duración (segundos entre rotaciones)",
        "settings.add_plugin": "+ Agregar plugin",
        "settings.plugin_config": "🔧 Configuración de plugins",
        "settings.plugin_name": "Plugin",
        "settings.plugin_weight": "Peso",
        "settings.plugin_weight_desc": "Mayor peso = más probabilidad de ser seleccionado. Establecer en 0 para desactivar.",
        "settings.plugin_remove": "Eliminar",

        // Connection status
        "status.connected": "Conectado",
        "status.disconnected": "Desconectado",

        // Config status
        "config.saving": "⏳ Guardando...",
        "config.saved": "✅ Guardado",
        "config.error": "❌ Error: ",
        "config.save_failed": "❌ Error al guardar",

        // Alerts
        "alert.enter_message": "Por favor ingrese un mensaje",
        "alert.export_failed": "Error al exportar ajustes: ",
        "alert.invalid_file": "Archivo de ajustes inválido: ",
        "alert.restore_confirm": "¿Restaurar ajustes desde esta copia?\nEsto sobrescribirá su configuración actual.",
        "alert.restore_success": "✅ Ajustes restaurados con éxito. Recargando...",
        "alert.restore_failed": "❌ Error al restaurar: ",

        // Boolean toggles
        "bool.yes": "Sí",
        "bool.no": "No",

        // GIF directories
        "gif.no_valid": "No se seleccionaron archivos GIF válidos",
        "gif.uploading": "Subiendo {count} archivo(s)...",
        "gif.no_dirs": "No se encontraron directorios. ¡Suba GIFs primero!",
        "gif.new_dir_prompt": "Nombre del nuevo directorio de GIFs:",

        // Location
        "location.no_results": "Sin resultados",

        // Misc
        "plugin.default_badge": "predeterminado",

        // Settings sidebar & theme
        "settings.cat_general": "General",
        "settings.cat_location": "Ubicación",
        "settings.cat_hardware": "Hardware",
        "settings.cat_connectivity": "Conectividad",
        "settings.cat_plugins": "Plugins",
        "settings.cat_plugin_config": "Configuración de plugins",
        "settings.theme_toggle": "Cambiar tema",
        "settings.theme_dark": "Oscuro",
        "settings.theme_light": "Claro",
        "config.save_failed_final": "Error al guardar tras reintentos. Cambio no aplicado.",
        "config.retry_failed": "Reintento fallido",
        "settings.backup_download": "Descargar copia de seguridad",
        "settings.backup_restore": "Restaurar copia de seguridad",
        "settings.file_too_large": "Archivo demasiado grande (máx. 1 MB)",
        "settings.invalid_json": "Archivo JSON inválido",
        "settings.cat_debug": "Debug",
        "settings.debug_system": "Info del sistema",
        "settings.debug_logs": "Logs en vivo",
        "settings.debug_refresh": "Actualizar",
    },
};

// Current language (default: English, updated from server config)
let currentLang = 'en';

/**
 * Get a translated string by key, with optional parameter substitution.
 * Falls back to English, then to the key itself.
 * @param {string} key - Translation key (e.g. "tab.dashboard")
 * @param {Object} [params] - Optional parameters for substitution (e.g. {count: 3})
 * @returns {string}
 */
function t(key, params) {
    let str = (translations[currentLang] && translations[currentLang][key])
        || translations.en[key]
        || key;
    if (params) {
        Object.keys(params).forEach(k => {
            str = str.replace(`{${k}}`, params[k]);
        });
    }
    return str;
}

/**
 * Set the current language and re-translate all static elements.
 * @param {string} lang - Language code (en, fr, de, es)
 */
function setLanguage(lang) {
    if (!translations[lang]) {
        console.warn(`i18n: unsupported language "${lang}", falling back to "en"`);
        lang = 'en';
    }
    currentLang = lang;
    document.documentElement.lang = lang;
    applyTranslations();
}

/**
 * Apply translations to all elements with data-i18n attributes.
 * Supports:
 *   data-i18n="key" → sets textContent
 *   data-i18n-placeholder="key" → sets placeholder
 *   data-i18n-title="key" → sets title attribute
 */
function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (key) el.textContent = t(key);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (key) el.placeholder = t(key);
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (key) el.title = t(key);
    });
}
