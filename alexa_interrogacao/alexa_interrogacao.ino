/*
 * Tecla Fantasma - gatilho por voz via Alexa
 *
 * Placa: NodeMCU 1.0 (ESP-12E), ou qualquer ESP8266
 *
 * O ESP se anuncia na rede como uma lampada Philips Hue. A Alexa descobre
 * lampada Hue sozinha, sem skill, sem conta, sem nuvem no meio do caminho -
 * por isso nao precisa de cadastro nenhum. Quando voce diz
 *
 *     "Alexa, ligar interrogacao"
 *
 * ela manda o comando de "ligar" pro ESP, que chama o endpoint HTTP do
 * tecla_fantasma.py no PC, e o PC digita o "?" na janela em foco.
 *
 * Latencia: 2 a 4 segundos. O reconhecimento de voz vai pra nuvem da Amazon e
 * volta - so o ultimo trecho e local. Serve como demo, nao pra escrever no
 * meio de uma frase. O botao fisico continua sendo o uso diario.
 *
 * Antes de gravar:  cp config.h.exemplo config.h  e preencha.
 * Biblioteca:       arduino-cli lib install Espalexa
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <Espalexa.h>

#include "config.h"

Espalexa espalexa;
WiFiClient cliente;

void aoComando(uint8_t brilho);

void setup() {
  Serial.begin(115200);
  Serial.println();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
  Serial.print("conectando no wifi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("conectado. IP do ESP: ");
  Serial.println(WiFi.localIP());

  espalexa.addDevice(NOME_ALEXA, aoComando);
  espalexa.begin();

  Serial.print("anunciado como lampada Hue: ");
  Serial.println(NOME_ALEXA);
  Serial.println("agora peca pra Alexa procurar dispositivos novos");
}

void loop() {
  espalexa.loop();
  delay(1);
}

/*
 * A Alexa manda 0 pra "desligar" e 1..255 pra "ligar"/brilho.
 *
 * Aqui nao existe estado pra manter - "?" e uma acao momentanea, nao uma luz
 * que fica acesa. Entao "desligar" nao faz nada, e depois de agir a gente
 * devolve o dispositivo pro estado desligado. Sem isso a Alexa acha que ja
 * esta ligado e o segundo "ligar interrogacao" nao dispara nada.
 */
void aoComando(uint8_t brilho) {
  if (brilho == 0) return;

  dispararTecla();

  EspalexaDevice *d = espalexa.getDevice(0);
  if (d != nullptr) d->setValue(0);
}

void dispararTecla() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("sem wifi, ignorando");
    return;
  }

  String url = "http://" PC_IP ":" + String(PC_PORTA) +
               "/k/interrogacao?token=" TOKEN;

  HTTPClient http;
  http.setTimeout(3000);          // nao trava o loop se o PC estiver desligado
  if (!http.begin(cliente, url)) {
    Serial.println("URL invalida, confira o config.h");
    return;
  }

  int codigo = http.GET();
  if (codigo == 200) {
    Serial.println("ok, PC digitou");
  } else if (codigo == 403) {
    Serial.println("403: TOKEN do config.h nao bate com TECLA_FANTASMA_TOKEN");
  } else if (codigo > 0) {
    Serial.printf("resposta inesperada: %d\n", codigo);
  } else {
    // Negativo = nem chegou a falar com o PC. Quase sempre uma destas tres:
    // IP errado no config.h, daemon rodando em 127.0.0.1 em vez de 0.0.0.0,
    // ou firewall do PC bloqueando a porta.
    Serial.printf("nao alcancou %s:%d (%s)\n", PC_IP, PC_PORTA,
                  http.errorToString(codigo).c_str());
  }
  http.end();
}
