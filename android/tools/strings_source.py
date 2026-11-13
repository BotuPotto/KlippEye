#!/usr/bin/env python3
"""
The texts of the app's own screens (splash, "Addresses" window, messages, notification channels) in the dashboard's ten
languages. Android picks the phone's language; English is the default (res/values/strings.xml).

    python3 tools/strings_source.py      writes app/src/main/res/values*/strings.xml

Edit the texts here, not in the XML files. The same register as the dashboard's translations: «tu» in Italian, Spanish,
German, Polish and Portuguese (Brazil), «vous» in French, «вы» in Russian and Ukrainian.
"""
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "app", "src", "main", "res")

# Android folder of each language (pt is Brazilian Portuguese, zh is Simplified Chinese, as in the dashboard)
FOLDERS = {"en": "values", "it": "values-it", "es": "values-es", "de": "values-de", "fr": "values-fr", "pt": "values-pt",
           "pl": "values-pl", "zh": "values-zh", "ru": "values-ru", "uk": "values-uk"}

T = {
    "app_name": {"en": "KlippEye"},
    "logo_description": {
        "en": "KlippEye logo", "it": "Logo di KlippEye", "es": "Logotipo de KlippEye", "de": "KlippEye-Logo", "fr": "Logo de KlippEye",
        "pt": "Logotipo do KlippEye", "pl": "Logo KlippEye", "zh": "KlippEye 标志", "ru": "Логотип KlippEye", "uk": "Логотип KlippEye"},
    "status_searching": {
        "en": "Looking for KlippEye…", "it": "Cerco KlippEye…", "es": "Buscando KlippEye…", "de": "Suche KlippEye…", "fr": "Recherche de KlippEye…",
        "pt": "Procurando o KlippEye…", "pl": "Szukam KlippEye…", "zh": "正在查找 KlippEye…", "ru": "Поиск KlippEye…", "uk": "Пошук KlippEye…"},
    "status_searching_local": {
        "en": "Looking for KlippEye on the home network…", "it": "Cerco KlippEye nella rete di casa…", "es": "Buscando KlippEye en la red de casa…",
        "de": "Suche KlippEye im Heimnetz…", "fr": "Recherche de KlippEye sur le réseau local…", "pt": "Procurando o KlippEye na rede de casa…",
        "pl": "Szukam KlippEye w sieci domowej…", "zh": "正在家庭网络中查找 KlippEye…", "ru": "Поиск KlippEye в домашней сети…", "uk": "Пошук KlippEye в домашній мережі…"},
    "status_first_start": {
        "en": "Enter the Raspberry's address to begin.", "it": "Scrivi l'indirizzo del Raspberry per cominciare.",
        "es": "Escribe la dirección de la Raspberry para empezar.", "de": "Gib die Adresse des Raspberry ein, um zu beginnen.",
        "fr": "Saisissez l'adresse du Raspberry pour commencer.", "pt": "Digite o endereço do Raspberry para começar.",
        "pl": "Wpisz adres Raspberry, aby zacząć.", "zh": "输入树莓派的地址以开始。", "ru": "Введите адрес Raspberry, чтобы начать.",
        "uk": "Введіть адресу Raspberry, щоб почати."},
    "status_attempt": {
        "en": "Attempt %1$d of %2$d: %3$s %4$s…", "it": "Tentativo %1$d di %2$d: %3$s %4$s…", "es": "Intento %1$d de %2$d: %3$s %4$s…",
        "de": "Versuch %1$d von %2$d: %3$s %4$s…", "fr": "Essai %1$d sur %2$d : %3$s %4$s…", "pt": "Tentativa %1$d de %2$d: %3$s %4$s…",
        "pl": "Próba %1$d z %2$d: %3$s %4$s…", "zh": "第 %1$d 次尝试（共 %2$d 次）：%3$s %4$s…", "ru": "Попытка %1$d из %2$d: %3$s %4$s…",
        "uk": "Спроба %1$d з %2$d: %3$s %4$s…"},
    "network_local": {
        "en": "home network", "it": "rete di casa", "es": "red de casa", "de": "Heimnetz", "fr": "réseau local", "pt": "rede de casa",
        "pl": "sieć domowa", "zh": "家庭网络", "ru": "домашняя сеть", "uk": "домашня мережа"},
    "network_external": {"en": "ZeroTier / VPN"},
    "status_connected": {
        "en": "Connected to %1$s", "it": "Connesso a %1$s", "es": "Conectado a %1$s", "de": "Verbunden mit %1$s", "fr": "Connecté à %1$s",
        "pt": "Conectado a %1$s", "pl": "Połączono z %1$s", "zh": "已连接到 %1$s", "ru": "Подключено к %1$s", "uk": "Підключено до %1$s"},
    "status_connected_via": {
        "en": "Connected via %1$s %2$s", "it": "Connesso tramite %1$s %2$s", "es": "Conectado mediante %1$s %2$s", "de": "Verbunden über %1$s %2$s",
        "fr": "Connecté via %1$s %2$s", "pt": "Conectado via %1$s %2$s", "pl": "Połączono przez %1$s %2$s", "zh": "已通过 %1$s %2$s 连接",
        "ru": "Подключено через %1$s %2$s", "uk": "Підключено через %1$s %2$s"},
    "status_switching": {
        "en": "%1$s does not answer, trying %2$s…", "it": "%1$s non risponde, provo %2$s…", "es": "%1$s no responde, probando %2$s…",
        "de": "%1$s antwortet nicht, versuche %2$s…", "fr": "%1$s ne répond pas, essai avec %2$s…", "pt": "%1$s não responde, tentando %2$s…",
        "pl": "%1$s nie odpowiada, próbuję: %2$s…", "zh": "%1$s 没有响应，正在尝试 %2$s…", "ru": "%1$s не отвечает, пробую %2$s…",
        "uk": "%1$s не відповідає, пробую %2$s…"},
    "status_not_answering": {
        "en": "KlippEye does not answer. Check that the Raspberry is on and connected to the network (and ZeroTier, if you use it), or check the addresses.",
        "it": "KlippEye non risponde. Controlla che il Raspberry sia acceso e in rete (e ZeroTier, se lo usi), oppure controlla gli indirizzi.",
        "es": "KlippEye no responde. Comprueba que la Raspberry esté encendida y conectada a la red (y ZeroTier, si lo usas), o revisa las direcciones.",
        "de": "KlippEye antwortet nicht. Prüfe, ob der Raspberry eingeschaltet und im Netz ist (und ZeroTier, falls du es nutzt), oder prüfe die Adressen.",
        "fr": "KlippEye ne répond pas. Vérifiez que le Raspberry est allumé et connecté au réseau (et ZeroTier, si vous l'utilisez), ou vérifiez les adresses.",
        "pt": "O KlippEye não responde. Verifique se o Raspberry está ligado e na rede (e o ZeroTier, se você usa), ou confira os endereços.",
        "pl": "KlippEye nie odpowiada. Sprawdź, czy Raspberry jest włączone i w sieci (oraz ZeroTier, jeśli go używasz), albo sprawdź adresy.",
        "zh": "KlippEye 没有响应。请检查树莓派是否已开机并连接网络（如使用 ZeroTier，也请检查它），或检查地址。",
        "ru": "KlippEye не отвечает. Проверьте, что Raspberry включён и подключён к сети (и ZeroTier, если вы его используете), или проверьте адреса.",
        "uk": "KlippEye не відповідає. Перевірте, що Raspberry увімкнений і підключений до мережі (і ZeroTier, якщо ви його використовуєте), або перевірте адреси."},
    "status_connecting_printer": {
        "en": "Connecting to %1$s…", "it": "Mi collego a %1$s…", "es": "Conectando con %1$s…", "de": "Verbinde mit %1$s…", "fr": "Connexion à %1$s…",
        "pt": "Conectando a %1$s…", "pl": "Łączę z %1$s…", "zh": "正在连接 %1$s…", "ru": "Подключение к %1$s…", "uk": "Підключення до %1$s…"},
    "printer_not_answering": {
        "en": "%1$s does not answer: back to the main printer", "it": "%1$s non risponde: torno alla stampante principale",
        "es": "%1$s no responde: vuelvo a la impresora principal", "de": "%1$s antwortet nicht: zurück zum Hauptdrucker",
        "fr": "%1$s ne répond pas : retour à l'imprimante principale", "pt": "%1$s não responde: voltando à impressora principal",
        "pl": "%1$s nie odpowiada: wracam do głównej drukarki", "zh": "%1$s 没有响应：返回主打印机", "ru": "%1$s не отвечает: возврат к основному принтеру",
        "uk": "%1$s не відповідає: повернення до основного принтера"},
    "retry": {
        "en": "Try again", "it": "Riprova", "es": "Reintentar", "de": "Erneut versuchen", "fr": "Réessayer", "pt": "Tentar de novo",
        "pl": "Ponów", "zh": "重试", "ru": "Повторить", "uk": "Повторити"},
    "addresses": {
        "en": "Addresses", "it": "Indirizzi", "es": "Direcciones", "de": "Adressen", "fr": "Adresses", "pt": "Endereços", "pl": "Adresy",
        "zh": "地址", "ru": "Адреса", "uk": "Адреси"},
    "cancel": {
        "en": "Cancel", "it": "Annulla", "es": "Cancelar", "de": "Abbrechen", "fr": "Annuler", "pt": "Cancelar", "pl": "Anuluj", "zh": "取消",
        "ru": "Отмена", "uk": "Скасувати"},
    "addresses_title": {
        "en": "Raspberry addresses", "it": "Indirizzi del Raspberry", "es": "Direcciones de la Raspberry", "de": "Adressen des Raspberry",
        "fr": "Adresses du Raspberry", "pt": "Endereços do Raspberry", "pl": "Adresy Raspberry", "zh": "树莓派地址", "ru": "Адреса Raspberry",
        "uk": "Адреси Raspberry"},
    "addresses_welcome_title": {
        "en": "Welcome to KlippEye", "it": "Benvenuto in KlippEye", "es": "Te damos la bienvenida a KlippEye", "de": "Willkommen bei KlippEye",
        "fr": "Bienvenue dans KlippEye", "pt": "Boas-vindas ao KlippEye", "pl": "Witaj w KlippEye", "zh": "欢迎使用 KlippEye",
        "ru": "Добро пожаловать в KlippEye", "uk": "Ласкаво просимо до KlippEye"},
    "addresses_welcome_message": {
        "en": "Where is your printer? %1$s", "it": "Dov'è la tua stampante? %1$s", "es": "¿Dónde está tu impresora? %1$s",
        "de": "Wo ist dein Drucker? %1$s", "fr": "Où est votre imprimante ? %1$s", "pt": "Onde está sua impressora? %1$s",
        "pl": "Gdzie jest twoja drukarka? %1$s", "zh": "你的打印机在哪里？%1$s", "ru": "Где ваш принтер? %1$s", "uk": "Де ваш принтер? %1$s"},
    "addresses_explanation": {
        "en": "The same address you use to open the printer's web page in the browser (without http:// and without a port), for example 192.168.1.20 or printer.local. The external address is needed only if you open KlippEye away from home with ZeroTier or a VPN.",
        "it": "Lo stesso indirizzo che usi per aprire la pagina web della stampante dal browser (senza http:// e senza porta), per esempio 192.168.1.20 oppure stampante.local. L'indirizzo esterno serve solo se apri KlippEye fuori casa con ZeroTier o una VPN.",
        "es": "La misma dirección que usas para abrir la página web de la impresora en el navegador (sin http:// y sin puerto), por ejemplo 192.168.1.20 o impresora.local. La dirección externa solo hace falta si abres KlippEye fuera de casa con ZeroTier o una VPN.",
        "de": "Dieselbe Adresse, mit der du die Webseite des Druckers im Browser öffnest (ohne http:// und ohne Port), zum Beispiel 192.168.1.20 oder drucker.local. Die externe Adresse brauchst du nur, wenn du KlippEye unterwegs über ZeroTier oder ein VPN öffnest.",
        "fr": "La même adresse que celle utilisée pour ouvrir la page web de l'imprimante dans le navigateur (sans http:// ni port), par exemple 192.168.1.20 ou imprimante.local. L'adresse externe ne sert que si vous ouvrez KlippEye hors de chez vous avec ZeroTier ou un VPN.",
        "pt": "O mesmo endereço que você usa para abrir a página web da impressora no navegador (sem http:// e sem porta), por exemplo 192.168.1.20 ou impressora.local. O endereço externo só é necessário se você abre o KlippEye fora de casa com ZeroTier ou uma VPN.",
        "pl": "Ten sam adres, którego używasz, aby otworzyć stronę drukarki w przeglądarce (bez http:// i bez portu), na przykład 192.168.1.20 lub drukarka.local. Adres zewnętrzny jest potrzebny tylko wtedy, gdy otwierasz KlippEye poza domem przez ZeroTier lub VPN.",
        "zh": "与在浏览器中打开打印机网页时使用的地址相同（不含 http:// 和端口），例如 192.168.1.20 或 printer.local。只有在家外通过 ZeroTier 或 VPN 打开 KlippEye 时才需要外部地址。",
        "ru": "Тот же адрес, по которому вы открываете веб-страницу принтера в браузере (без http:// и без порта), например 192.168.1.20 или printer.local. Внешний адрес нужен, только если вы открываете KlippEye вне дома через ZeroTier или VPN.",
        "uk": "Та сама адреса, за якою ви відкриваєте вебсторінку принтера в браузері (без http:// і без порту), наприклад 192.168.1.20 або printer.local. Зовнішня адреса потрібна, лише якщо ви відкриваєте KlippEye поза домом через ZeroTier або VPN."},
    "addresses_hint_local": {
        "en": "Local IP, e.g. 192.168.1.20", "it": "IP locale, es. 192.168.1.20", "es": "IP local, p. ej. 192.168.1.20", "de": "Lokale IP, z. B. 192.168.1.20",
        "fr": "IP locale, p. ex. 192.168.1.20", "pt": "IP local, ex.: 192.168.1.20", "pl": "Lokalny IP, np. 192.168.1.20", "zh": "本地 IP，例如 192.168.1.20",
        "ru": "Локальный IP, напр. 192.168.1.20", "uk": "Локальна IP, напр. 192.168.1.20"},
    "addresses_hint_external": {
        "en": "External IP (optional: ZeroTier, VPN)", "it": "IP esterno (facoltativo: ZeroTier, VPN)", "es": "IP externa (opcional: ZeroTier, VPN)",
        "de": "Externe IP (optional: ZeroTier, VPN)", "fr": "IP externe (facultatif : ZeroTier, VPN)", "pt": "IP externo (opcional: ZeroTier, VPN)",
        "pl": "Zewnętrzny IP (opcjonalnie: ZeroTier, VPN)", "zh": "外部 IP（可选：ZeroTier、VPN）", "ru": "Внешний IP (необязательно: ZeroTier, VPN)",
        "uk": "Зовнішня IP (необов'язково: ZeroTier, VPN)"},
    "addresses_connect": {
        "en": "Connect", "it": "Collegati", "es": "Conectar", "de": "Verbinden", "fr": "Se connecter", "pt": "Conectar", "pl": "Połącz", "zh": "连接",
        "ru": "Подключиться", "uk": "Підключитися"},
    "addresses_save": {
        "en": "Save and try again", "it": "Salva e riprova", "es": "Guardar y reintentar", "de": "Speichern und erneut versuchen",
        "fr": "Enregistrer et réessayer", "pt": "Salvar e tentar de novo", "pl": "Zapisz i ponów", "zh": "保存并重试", "ru": "Сохранить и повторить",
        "uk": "Зберегти й повторити"},
    "address_local_invalid": {
        "en": "The local IP is not a valid address", "it": "L'IP locale non è un indirizzo valido", "es": "La IP local no es una dirección válida",
        "de": "Die lokale IP ist keine gültige Adresse", "fr": "L'IP locale n'est pas une adresse valide", "pt": "O IP local não é um endereço válido",
        "pl": "Lokalny IP nie jest prawidłowym adresem", "zh": "本地 IP 不是有效地址", "ru": "Локальный IP — недопустимый адрес",
        "uk": "Локальна IP — недійсна адреса"},
    "address_local_not_private": {
        "en": "The local IP must belong to a private network (192.168.x.x, 10.x.x.x, 172.16-31.x.x)",
        "it": "L'IP locale deve essere di una rete privata (192.168.x.x, 10.x.x.x, 172.16-31.x.x)",
        "es": "La IP local debe ser de una red privada (192.168.x.x, 10.x.x.x, 172.16-31.x.x)",
        "de": "Die lokale IP muss zu einem privaten Netz gehören (192.168.x.x, 10.x.x.x, 172.16-31.x.x)",
        "fr": "L'IP locale doit appartenir à un réseau privé (192.168.x.x, 10.x.x.x, 172.16-31.x.x)",
        "pt": "O IP local precisa ser de uma rede privada (192.168.x.x, 10.x.x.x, 172.16-31.x.x)",
        "pl": "Lokalny IP musi należeć do sieci prywatnej (192.168.x.x, 10.x.x.x, 172.16-31.x.x)",
        "zh": "本地 IP 必须属于私有网络（192.168.x.x、10.x.x.x、172.16-31.x.x）",
        "ru": "Локальный IP должен принадлежать частной сети (192.168.x.x, 10.x.x.x, 172.16-31.x.x)",
        "uk": "Локальна IP має належати до приватної мережі (192.168.x.x, 10.x.x.x, 172.16-31.x.x)"},
    "address_external_invalid": {
        "en": "The external IP is not a valid address", "it": "L'IP esterno non è un indirizzo valido", "es": "La IP externa no es una dirección válida",
        "de": "Die externe IP ist keine gültige Adresse", "fr": "L'IP externe n'est pas une adresse valide", "pt": "O IP externo não é um endereço válido",
        "pl": "Zewnętrzny IP nie jest prawidłowym adresem", "zh": "外部 IP 不是有效地址", "ru": "Внешний IP — недопустимый адрес",
        "uk": "Зовнішня IP — недійсна адреса"},
    "address_external_not_private": {
        "en": "The external IP must belong to a private network (ZeroTier, VPN)", "it": "L'IP esterno deve essere di una rete privata (ZeroTier, VPN)",
        "es": "La IP externa debe ser de una red privada (ZeroTier, VPN)", "de": "Die externe IP muss zu einem privaten Netz gehören (ZeroTier, VPN)",
        "fr": "L'IP externe doit appartenir à un réseau privé (ZeroTier, VPN)", "pt": "O IP externo precisa ser de uma rede privada (ZeroTier, VPN)",
        "pl": "Zewnętrzny IP musi należeć do sieci prywatnej (ZeroTier, VPN)", "zh": "外部 IP 必须属于私有网络（ZeroTier、VPN）",
        "ru": "Внешний IP должен принадлежать частной сети (ZeroTier, VPN)", "uk": "Зовнішня IP має належати до приватної мережі (ZeroTier, VPN)"},
    "link_install_ntfy": {
        "en": "Install the ntfy app first", "it": "Installa prima l'app ntfy", "es": "Instala primero la app ntfy", "de": "Installiere zuerst die App ntfy",
        "fr": "Installez d'abord l'appli ntfy", "pt": "Instale primeiro o app ntfy", "pl": "Najpierw zainstaluj aplikację ntfy", "zh": "请先安装 ntfy 应用",
        "ru": "Сначала установите приложение ntfy", "uk": "Спершу встановіть застосунок ntfy"},
    "link_no_app": {
        "en": "No app can open this link", "it": "Nessuna app può aprire questo collegamento", "es": "Ninguna app puede abrir este enlace",
        "de": "Keine App kann diesen Link öffnen", "fr": "Aucune appli ne peut ouvrir ce lien", "pt": "Nenhum app consegue abrir este link",
        "pl": "Żadna aplikacja nie może otworzyć tego linku", "zh": "没有应用可以打开此链接", "ru": "Нет приложения, которое может открыть эту ссылку",
        "uk": "Немає застосунку, який може відкрити це посилання"},
    "battery_settings_hint": {
        "en": "Open Settings > Apps > KlippEye > Battery and choose «Unrestricted»",
        "it": "Apri Impostazioni > App > KlippEye > Batteria e scegli «Senza limitazioni»",
        "es": "Abre Ajustes > Aplicaciones > KlippEye > Batería y elige «Sin restricciones»",
        "de": "Öffne Einstellungen > Apps > KlippEye > Akku und wähle «Nicht eingeschränkt»",
        "fr": "Ouvrez Paramètres > Applis > KlippEye > Batterie et choisissez «Non restreinte»",
        "pt": "Abra Configurações > Apps > KlippEye > Bateria e escolha «Sem restrições»",
        "pl": "Otwórz Ustawienia > Aplikacje > KlippEye > Bateria i wybierz „Bez ograniczeń”",
        "zh": "请打开“设置 > 应用 > KlippEye > 电池”，然后选择“无限制”",
        "ru": "Откройте Настройки > Приложения > KlippEye > Батарея и выберите «Без ограничений»",
        "uk": "Відкрийте Налаштування > Застосунки > KlippEye > Акумулятор і виберіть «Без обмежень»"},
    "notification_settings_hint": {
        "en": "Open Settings > Apps > KlippEye > Notifications", "it": "Apri Impostazioni > App > KlippEye > Notifiche",
        "es": "Abre Ajustes > Aplicaciones > KlippEye > Notificaciones", "de": "Öffne Einstellungen > Apps > KlippEye > Benachrichtigungen",
        "fr": "Ouvrez Paramètres > Applis > KlippEye > Notifications", "pt": "Abra Configurações > Apps > KlippEye > Notificações",
        "pl": "Otwórz Ustawienia > Aplikacje > KlippEye > Powiadomienia", "zh": "请打开“设置 > 应用 > KlippEye > 通知”",
        "ru": "Откройте Настройки > Приложения > KlippEye > Уведомления", "uk": "Відкрийте Налаштування > Застосунки > KlippEye > Сповіщення"},
    "install_permission_hint": {
        "en": "Open Settings > Apps > KlippEye > Install unknown apps, allow it, then try again",
        "it": "Apri Impostazioni > App > KlippEye > Installa app sconosciute, consenti e poi riprova",
        "es": "Abre Ajustes > Aplicaciones > KlippEye > Instalar apps desconocidas, permítelo y vuelve a intentarlo",
        "de": "Öffne Einstellungen > Apps > KlippEye > Unbekannte Apps installieren, erlaube es und versuche es erneut",
        "fr": "Ouvrez Paramètres > Applis > KlippEye > Installer des applis inconnues, autorisez-le puis réessayez",
        "pt": "Abra Configurações > Apps > KlippEye > Instalar apps desconhecidos, permita e tente de novo",
        "pl": "Otwórz Ustawienia > Aplikacje > KlippEye > Instalowanie nieznanych aplikacji, zezwól i spróbuj ponownie",
        "zh": "请打开“设置 > 应用 > KlippEye > 安装未知应用”，允许后重试",
        "ru": "Откройте Настройки > Приложения > KlippEye > Установка неизвестных приложений, разрешите и повторите попытку",
        "uk": "Відкрийте Налаштування > Застосунки > KlippEye > Встановлення невідомих застосунків, дозвольте й повторіть спробу"},
    "install_permission_missing": {
        "en": "Without the permission Android does not install the update: turn on «Allow from this source» for KlippEye and try again",
        "it": "Senza il permesso Android non installa l'aggiornamento: attiva «Consenti da questa fonte» per KlippEye e riprova",
        "es": "Sin el permiso Android no instala la actualización: activa «Permitir de esta fuente» para KlippEye y vuelve a intentarlo",
        "de": "Ohne die Berechtigung installiert Android das Update nicht: Schalte «Aus dieser Quelle zulassen» für KlippEye ein und versuche es erneut",
        "fr": "Sans l'autorisation, Android n'installe pas la mise à jour : activez «Autoriser cette source» pour KlippEye et réessayez",
        "pt": "Sem a permissão o Android não instala a atualização: ative «Permitir desta fonte» para o KlippEye e tente de novo",
        "pl": "Bez uprawnienia Android nie zainstaluje aktualizacji: włącz „Zezwalaj z tego źródła” dla KlippEye i spróbuj ponownie",
        "zh": "没有该权限，Android 不会安装更新：请为 KlippEye 开启“允许来自此来源的应用”，然后重试",
        "ru": "Без разрешения Android не установит обновление: включите «Разрешить установку из этого источника» для KlippEye и повторите попытку",
        "uk": "Без дозволу Android не встановить оновлення: увімкніть «Дозволити з цього джерела» для KlippEye і повторіть спробу"},
    "installer_failed": {
        "en": "Android's installer could not be opened: %1$s", "it": "Non riesco ad aprire l'installazione di Android: %1$s",
        "es": "No se pudo abrir el instalador de Android: %1$s", "de": "Der Android-Installer konnte nicht geöffnet werden: %1$s",
        "fr": "Impossible d'ouvrir le programme d'installation d'Android : %1$s", "pt": "Não foi possível abrir o instalador do Android: %1$s",
        "pl": "Nie udało się otworzyć instalatora Androida: %1$s", "zh": "无法打开 Android 安装程序：%1$s",
        "ru": "Не удалось открыть установщик Android: %1$s", "uk": "Не вдалося відкрити інсталятор Android: %1$s"},
    "update_error_connection": {
        "en": "The connection to the Raspberry was lost: %1$s", "it": "Il collegamento con il Raspberry si è interrotto: %1$s",
        "es": "Se perdió la conexión con la Raspberry: %1$s", "de": "Die Verbindung zum Raspberry wurde unterbrochen: %1$s",
        "fr": "La connexion au Raspberry a été interrompue : %1$s", "pt": "A conexão com o Raspberry caiu: %1$s",
        "pl": "Połączenie z Raspberry zostało przerwane: %1$s", "zh": "与树莓派的连接已中断：%1$s",
        "ru": "Связь с Raspberry прервалась: %1$s", "uk": "Зв'язок із Raspberry перервався: %1$s"},
    "update_error_bad_address": {
        "en": "The update's address is not valid", "it": "L'indirizzo dell'aggiornamento non è valido", "es": "La dirección de la actualización no es válida",
        "de": "Die Adresse des Updates ist ungültig", "fr": "L'adresse de la mise à jour n'est pas valide", "pt": "O endereço da atualização não é válido",
        "pl": "Adres aktualizacji jest nieprawidłowy", "zh": "更新地址无效", "ru": "Адрес обновления недопустим", "uk": "Адреса оновлення недійсна"},
    "update_error_other_server": {
        "en": "The app downloads updates only from the Raspberry it is connected to", "it": "L'app scarica gli aggiornamenti solo dal Raspberry a cui è collegata",
        "es": "La app solo descarga actualizaciones de la Raspberry a la que está conectada", "de": "Die App lädt Updates nur von dem Raspberry, mit dem sie verbunden ist",
        "fr": "L'appli ne télécharge les mises à jour que depuis le Raspberry auquel elle est connectée", "pt": "O app só baixa atualizações do Raspberry ao qual está conectado",
        "pl": "Aplikacja pobiera aktualizacje tylko z Raspberry, z którym jest połączona", "zh": "应用只从已连接的树莓派下载更新",
        "ru": "Приложение загружает обновления только с Raspberry, к которому подключено", "uk": "Застосунок завантажує оновлення лише з Raspberry, до якого підключений"},
    "update_error_bad_version": {
        "en": "The version number is not valid", "it": "Il numero di versione non è valido", "es": "El número de versión no es válido",
        "de": "Die Versionsnummer ist ungültig", "fr": "Le numéro de version n'est pas valide", "pt": "O número da versão não é válido",
        "pl": "Numer wersji jest nieprawidłowy", "zh": "版本号无效", "ru": "Номер версии недопустим", "uk": "Номер версії недійсний"},
    "update_error_up_to_date": {
        "en": "The app is already up to date", "it": "L'app è già aggiornata", "es": "La app ya está actualizada", "de": "Die App ist bereits aktuell",
        "fr": "L'appli est déjà à jour", "pt": "O app já está atualizado", "pl": "Aplikacja jest już aktualna", "zh": "应用已是最新版本",
        "ru": "Приложение уже обновлено", "uk": "Застосунок уже оновлено"},
    "update_error_no_fingerprint": {
        "en": "The file's fingerprint is missing: check for updates again", "it": "Manca l'impronta del file: controlla di nuovo gli aggiornamenti",
        "es": "Falta la huella del archivo: vuelve a buscar actualizaciones", "de": "Der Fingerabdruck der Datei fehlt: suche erneut nach Updates",
        "fr": "L'empreinte du fichier manque : recherchez à nouveau les mises à jour", "pt": "Falta a impressão digital do arquivo: verifique as atualizações de novo",
        "pl": "Brak odcisku pliku: ponownie sprawdź aktualizacje", "zh": "缺少文件指纹：请重新检查更新",
        "ru": "Нет отпечатка файла: проверьте обновления ещё раз", "uk": "Немає відбитка файлу: перевірте оновлення ще раз"},
    "update_error_bad_size": {
        "en": "The file size is not valid", "it": "La grandezza del file non è valida", "es": "El tamaño del archivo no es válido",
        "de": "Die Dateigröße ist ungültig", "fr": "La taille du fichier n'est pas valide", "pt": "O tamanho do arquivo não é válido",
        "pl": "Rozmiar pliku jest nieprawidłowy", "zh": "文件大小无效", "ru": "Размер файла недопустим", "uk": "Розмір файлу недійсний"},
    "update_error_no_storage": {
        "en": "The phone's storage is not available", "it": "La memoria del telefono non è disponibile", "es": "El almacenamiento del teléfono no está disponible",
        "de": "Der Speicher des Telefons ist nicht verfügbar", "fr": "Le stockage du téléphone n'est pas disponible", "pt": "O armazenamento do celular não está disponível",
        "pl": "Pamięć telefonu jest niedostępna", "zh": "手机存储不可用", "ru": "Память телефона недоступна", "uk": "Пам'ять телефона недоступна"},
    "update_error_no_apk": {
        "en": "The Raspberry does not have the app: update KlippEye first, then check again", "it": "Il Raspberry non ha l'app: aggiorna prima KlippEye, poi controlla di nuovo",
        "es": "La Raspberry no tiene la app: actualiza primero KlippEye y vuelve a comprobar", "de": "Der Raspberry hat die App nicht: aktualisiere zuerst KlippEye und prüfe dann erneut",
        "fr": "Le Raspberry n'a pas l'appli : mettez d'abord KlippEye à jour, puis vérifiez à nouveau", "pt": "O Raspberry não tem o app: atualize primeiro o KlippEye e verifique de novo",
        "pl": "Raspberry nie ma aplikacji: najpierw zaktualizuj KlippEye, potem sprawdź ponownie", "zh": "树莓派上没有该应用：请先更新 KlippEye，然后重新检查",
        "ru": "На Raspberry нет приложения: сначала обновите KlippEye, затем проверьте снова", "uk": "На Raspberry немає застосунку: спершу оновіть KlippEye, потім перевірте знову"},
    "update_error_http": {
        "en": "The Raspberry answered with an error (%1$s)", "it": "Il Raspberry ha risposto con un errore (%1$s)", "es": "La Raspberry respondió con un error (%1$s)",
        "de": "Der Raspberry hat mit einem Fehler geantwortet (%1$s)", "fr": "Le Raspberry a répondu par une erreur (%1$s)", "pt": "O Raspberry respondeu com um erro (%1$s)",
        "pl": "Raspberry odpowiedziało błędem (%1$s)", "zh": "树莓派返回了错误（%1$s）", "ru": "Raspberry ответил ошибкой (%1$s)", "uk": "Raspberry відповів помилкою (%1$s)"},
    "update_error_not_announced": {
        "en": "The file on the Raspberry is not the announced one: check for updates again", "it": "Il file sul Raspberry non è quello annunciato: controlla di nuovo gli aggiornamenti",
        "es": "El archivo de la Raspberry no es el anunciado: vuelve a buscar actualizaciones", "de": "Die Datei auf dem Raspberry ist nicht die angekündigte: suche erneut nach Updates",
        "fr": "Le fichier du Raspberry n'est pas celui annoncé : recherchez à nouveau les mises à jour", "pt": "O arquivo no Raspberry não é o anunciado: verifique as atualizações de novo",
        "pl": "Plik na Raspberry nie jest tym zapowiedzianym: ponownie sprawdź aktualizacje", "zh": "树莓派上的文件与公布的不一致：请重新检查更新",
        "ru": "Файл на Raspberry не тот, что был объявлен: проверьте обновления ещё раз", "uk": "Файл на Raspberry не той, що був оголошений: перевірте оновлення ще раз"},
    "update_error_too_big": {
        "en": "The file is bigger than expected", "it": "Il file è più grande del previsto", "es": "El archivo es más grande de lo previsto",
        "de": "Die Datei ist größer als erwartet", "fr": "Le fichier est plus gros que prévu", "pt": "O arquivo é maior do que o esperado",
        "pl": "Plik jest większy niż oczekiwano", "zh": "文件比预期大", "ru": "Файл больше ожидаемого", "uk": "Файл більший, ніж очікувалося"},
    "update_error_interrupted": {
        "en": "The download stopped halfway (%1$s bytes): try again", "it": "Lo scaricamento si è interrotto a metà (%1$s byte): riprova",
        "es": "La descarga se interrumpió a medias (%1$s bytes): vuelve a intentarlo", "de": "Der Download wurde unterbrochen (%1$s Bytes): versuche es erneut",
        "fr": "Le téléchargement s'est arrêté en cours de route (%1$s octets) : réessayez", "pt": "O download parou no meio (%1$s bytes): tente de novo",
        "pl": "Pobieranie przerwało się w połowie (%1$s bajtów): spróbuj ponownie", "zh": "下载中途中断（%1$s 字节）：请重试",
        "ru": "Загрузка прервалась (%1$s байт): повторите попытку", "uk": "Завантаження перервалося (%1$s байтів): повторіть спробу"},
    "update_error_damaged": {
        "en": "The downloaded file is damaged (different fingerprint): try again", "it": "Il file scaricato è rovinato (impronta diversa): riprova",
        "es": "El archivo descargado está dañado (huella distinta): vuelve a intentarlo", "de": "Die heruntergeladene Datei ist beschädigt (anderer Fingerabdruck): versuche es erneut",
        "fr": "Le fichier téléchargé est endommagé (empreinte différente) : réessayez", "pt": "O arquivo baixado está corrompido (impressão digital diferente): tente de novo",
        "pl": "Pobrany plik jest uszkodzony (inny odcisk): spróbuj ponownie", "zh": "下载的文件已损坏（指纹不同）：请重试",
        "ru": "Загруженный файл повреждён (другой отпечаток): повторите попытку", "uk": "Завантажений файл пошкоджено (інший відбиток): повторіть спробу"},
    "update_error_cannot_save": {
        "en": "The file cannot be saved in the phone's storage", "it": "Il file non si può salvare nella memoria del telefono",
        "es": "No se puede guardar el archivo en el almacenamiento del teléfono", "de": "Die Datei kann nicht im Speicher des Telefons gespeichert werden",
        "fr": "Impossible d'enregistrer le fichier dans le stockage du téléphone", "pt": "Não é possível salvar o arquivo no armazenamento do celular",
        "pl": "Nie można zapisać pliku w pamięci telefonu", "zh": "无法将文件保存到手机存储", "ru": "Не удаётся сохранить файл в памяти телефона",
        "uk": "Не вдається зберегти файл у пам'яті телефона"},
    "download_not_supported": {
        "en": "This address cannot be downloaded", "it": "Questo indirizzo non si può scaricare", "es": "Esta dirección no se puede descargar",
        "de": "Diese Adresse kann nicht heruntergeladen werden", "fr": "Cette adresse ne peut pas être téléchargée", "pt": "Este endereço não pode ser baixado",
        "pl": "Tego adresu nie można pobrać", "zh": "无法下载此地址", "ru": "Этот адрес нельзя загрузить", "uk": "Цю адресу не можна завантажити"},
    "download_started": {
        "en": "Downloading %1$s…", "it": "Scarico %1$s…", "es": "Descargando %1$s…", "de": "Lade %1$s herunter…", "fr": "Téléchargement de %1$s…",
        "pt": "Baixando %1$s…", "pl": "Pobieram %1$s…", "zh": "正在下载 %1$s…", "ru": "Загрузка %1$s…", "uk": "Завантаження %1$s…"},
    "download_saved": {
        "en": "Saved in %1$s", "it": "Salvato in %1$s", "es": "Guardado en %1$s", "de": "Gespeichert in %1$s", "fr": "Enregistré dans %1$s",
        "pt": "Salvo em %1$s", "pl": "Zapisano w %1$s", "zh": "已保存到 %1$s", "ru": "Сохранено в %1$s", "uk": "Збережено в %1$s"},
    "download_failed": {
        "en": "Download failed: %1$s", "it": "Download non riuscito: %1$s", "es": "La descarga falló: %1$s", "de": "Download fehlgeschlagen: %1$s",
        "fr": "Échec du téléchargement : %1$s", "pt": "Falha no download: %1$s", "pl": "Pobieranie nie powiodło się: %1$s", "zh": "下载失败：%1$s",
        "ru": "Не удалось загрузить: %1$s", "uk": "Не вдалося завантажити: %1$s"},
    "channel_alarms": {
        "en": "Alarms and failures", "it": "Allarmi e guasti", "es": "Alarmas y fallos", "de": "Alarme und Fehler", "fr": "Alarmes et pannes",
        "pt": "Alarmes e falhas", "pl": "Alarmy i awarie", "zh": "警报和故障", "ru": "Тревоги и сбои", "uk": "Тривоги та збої"},
    "channel_alarms_description": {
        "en": "Printer error, filament run out, serious defects found by the AI", "it": "Stampante in errore, filamento esaurito, difetti gravi trovati dall'IA",
        "es": "Error de la impresora, filamento agotado, defectos graves detectados por la IA", "de": "Druckerfehler, Filament leer, schwere Fehler von der KI erkannt",
        "fr": "Imprimante en erreur, filament épuisé, défauts graves détectés par l'IA", "pt": "Erro da impressora, filamento acabou, defeitos graves detectados pela IA",
        "pl": "Błąd drukarki, koniec filamentu, poważne wady wykryte przez AI", "zh": "打印机错误、耗材用完、AI 发现严重缺陷",
        "ru": "Ошибка принтера, закончился филамент, серьёзные дефекты, найденные ИИ", "uk": "Помилка принтера, закінчився філамент, серйозні дефекти, знайдені ШІ"},
    "channel_warnings": {
        "en": "Warnings", "it": "Avvisi", "es": "Avisos", "de": "Warnungen", "fr": "Avertissements", "pt": "Avisos", "pl": "Ostrzeżenia", "zh": "提醒",
        "ru": "Предупреждения", "uk": "Попередження"},
    "channel_warnings_description": {
        "en": "Print paused or stopped, defects found by the AI", "it": "Stampa in pausa o interrotta, difetti trovati dall'IA",
        "es": "Impresión en pausa o detenida, defectos detectados por la IA", "de": "Druck pausiert oder abgebrochen, Fehler von der KI erkannt",
        "fr": "Impression en pause ou interrompue, défauts détectés par l'IA", "pt": "Impressão pausada ou interrompida, defeitos detectados pela IA",
        "pl": "Wydruk wstrzymany lub przerwany, wady wykryte przez AI", "zh": "打印暂停或中断、AI 发现缺陷",
        "ru": "Печать приостановлена или прервана, дефекты, найденные ИИ", "uk": "Друк призупинено або перервано, дефекти, знайдені ШІ"},
    "channel_print": {
        "en": "Print complete", "it": "Stampa completata", "es": "Impresión terminada", "de": "Druck fertig", "fr": "Impression terminée",
        "pt": "Impressão concluída", "pl": "Wydruk ukończony", "zh": "打印完成", "ru": "Печать завершена", "uk": "Друк завершено"},
    "channel_print_description": {
        "en": "End of print and test notifications", "it": "Fine stampa e notifiche di prova", "es": "Fin de impresión y notificaciones de prueba",
        "de": "Druckende und Testbenachrichtigungen", "fr": "Fin d'impression et notifications de test", "pt": "Fim da impressão e notificações de teste",
        "pl": "Koniec wydruku i powiadomienia testowe", "zh": "打印结束和测试通知", "ru": "Окончание печати и тестовые уведомления",
        "uk": "Закінчення друку й тестові сповіщення"},
    "channel_listening": {
        "en": "KlippEye is listening", "it": "KlippEye in ascolto", "es": "KlippEye a la escucha", "de": "KlippEye empfangsbereit", "fr": "KlippEye à l'écoute",
        "pt": "KlippEye ouvindo", "pl": "KlippEye nasłuchuje", "zh": "KlippEye 正在接收", "ru": "KlippEye на связи", "uk": "KlippEye на зв'язку"},
    "channel_listening_description": {
        "en": "The ongoing notification that keeps the connection open to receive the notifications. It can be hidden.",
        "it": "La notifica fissa che tiene aperto il collegamento per ricevere le notifiche. Si può nascondere.",
        "es": "La notificación fija que mantiene abierta la conexión para recibir las notificaciones. Se puede ocultar.",
        "de": "Die dauerhafte Benachrichtigung, die die Verbindung für den Empfang offen hält. Sie kann ausgeblendet werden.",
        "fr": "La notification permanente qui garde la connexion ouverte pour recevoir les notifications. Elle peut être masquée.",
        "pt": "A notificação fixa que mantém a conexão aberta para receber as notificações. Pode ser ocultada.",
        "pl": "Stałe powiadomienie, które utrzymuje otwarte połączenie, by odbierać powiadomienia. Można je ukryć.",
        "zh": "保持连接以接收通知的常驻通知。可以将其隐藏。",
        "ru": "Постоянное уведомление, которое держит соединение открытым для получения уведомлений. Его можно скрыть.",
        "uk": "Постійне сповіщення, яке тримає з'єднання відкритим для отримання сповіщень. Його можна приховати."},
    "listening_title": {
        "en": "KlippEye is listening", "it": "KlippEye in ascolto", "es": "KlippEye a la escucha", "de": "KlippEye empfangsbereit", "fr": "KlippEye à l'écoute",
        "pt": "KlippEye ouvindo", "pl": "KlippEye nasłuchuje", "zh": "KlippEye 正在接收", "ru": "KlippEye на связи", "uk": "KlippEye на зв'язку"},
    "listening_text": {
        "en": "Receives the printers' notifications. Touch and hold to hide it.", "it": "Riceve le notifiche delle stampanti. Tieni premuto per nasconderla.",
        "es": "Recibe las notificaciones de las impresoras. Mantén pulsado para ocultarla.", "de": "Empfängt die Benachrichtigungen der Drucker. Gedrückt halten zum Ausblenden.",
        "fr": "Reçoit les notifications des imprimantes. Appuyez longuement pour la masquer.", "pt": "Recebe as notificações das impressoras. Toque e segure para ocultá-la.",
        "pl": "Odbiera powiadomienia z drukarek. Przytrzymaj, aby je ukryć.", "zh": "接收打印机通知。长按可隐藏。",
        "ru": "Получает уведомления принтеров. Нажмите и удерживайте, чтобы скрыть.", "uk": "Отримує сповіщення принтерів. Натисніть і утримуйте, щоб приховати."},
}

# Texts that are the same in every language (names): only in values/, marked not to be translated
SAME_EVERYWHERE = {"app_name", "network_external"}


def android_escape(text):
    """XML escaping plus what Android's resource compiler needs: apostrophes and quotes escaped, a leading @ or ? too."""
    text = escape(text).replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
    return "\\" + text if text[:1] in "@?" else text


def main():
    for lang, folder in FOLDERS.items():
        lines = ['<?xml version="1.0" encoding="utf-8"?>',
                 "<!-- Written by android/tools/strings_source.py: edit the texts there. -->", "<resources>"]
        for key, texts in T.items():
            if key in SAME_EVERYWHERE:
                if lang == "en":
                    lines.append('    <string name="%s" translatable="false">%s</string>' % (key, android_escape(texts["en"])))
                continue
            if lang not in texts:
                raise SystemExit("missing %s in %s" % (key, lang))
            lines.append('    <string name="%s">%s</string>' % (key, android_escape(texts[lang])))
        lines.append("</resources>")
        path = os.path.join(RES, folder, "strings.xml")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("written", os.path.relpath(path, os.path.join(HERE, "..")))


if __name__ == "__main__":
    main()
