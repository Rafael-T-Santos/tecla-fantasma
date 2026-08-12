/*
 * Diagnostico: o que o radio do ESP8266 enxerga.
 *
 * Grave isto ANTES do firmware da Alexa quando houver duvida sobre wifi.
 * O ESP8266 so tem radio de 2.4 GHz, entao TUDO que aparecer nesta lista e
 * 2.4 GHz por definicao - e se uma rede nao aparecer aqui, ele nao vai
 * conseguir conectar nela, ponto.
 *
 * Isso vale mais que o scan do notebook: o `netsh wlan show networks` mostra
 * o ultimo scan em cache, e o Windows costuma nao varrer as outras bandas
 * enquanto ja esta associado a um AP.
 *
 *     .\gravar.ps1 -Placa nodemcu -Sketch scan_wifi
 *
 * Depois abra o monitor serial a 115200.
 */

#include <ESP8266WiFi.h>

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println();

  // Modo estacao e desassociado: scan enquanto conectado vem incompleto,
  // que e exatamente o vies do scan do Windows que motivou este sketch.
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(200);
}

void loop() {
  Serial.println("escaneando (tudo aqui e 2.4 GHz)...");

  // async=false, show_hidden=true - rede IoT costuma ocultar o SSID, e sem
  // isso ela nao apareceria e a gente concluiria errado que nao existe.
  int n = WiFi.scanNetworks(false, true);

  if (n <= 0) {
    Serial.println("  nenhuma rede encontrada");
  } else {
    Serial.printf("  %d redes:\n\n", n);
    Serial.println("  RSSI  CANAL  SEG    SSID");
    Serial.println("  ----  -----  -----  --------------------------------");
    for (int i = 0; i < n; i++) {
      String ssid = WiFi.SSID(i);
      bool oculta = (ssid.length() == 0);

      Serial.printf("  %4d  %5d  %-5s  %s\n",
                    WiFi.RSSI(i),
                    WiFi.channel(i),
                    WiFi.encryptionType(i) == ENC_TYPE_NONE ? "aberta" : "wpa",
                    oculta ? "(oculta)" : ssid.c_str());
    }
    Serial.println();
    Serial.println("  RSSI: -30 otimo, -67 bom, -80 fraco, -90 inutilizavel");
  }

  WiFi.scanDelete();
  Serial.println("\nrepetindo em 10s...\n");
  delay(10000);
}
