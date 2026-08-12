/*
 * Tecla Fantasma - botao fisico
 *
 * Placa: Arduino Nano (serve igual em Uno e Mega)
 *
 * Ligacao - so isso, sem resistor:
 *
 *     D2  ----[ botao ]---- GND
 *
 * O INPUT_PULLUP interno segura o pino em HIGH; apertar puxa pra LOW.
 * Nada de resistor externo, nada de 5V no botao.
 *
 * A placa so anuncia "apertei" pela serial. Quem digita de verdade e o
 * tecla_fantasma.py rodando no PC - o Nano nao tem USB HID, entao ele nao
 * consegue se passar por teclado sozinho.
 */

const uint8_t PINO_BOTAO = 2;

// Tempo que o sinal precisa ficar estavel pra contar como aperto de verdade.
// Contato mecanico "treme" por alguns ms ao fechar; sem isso um aperto vira
// varios "?" na tela.
const unsigned long DEBOUNCE_MS = 40;

int leituraEstavel = HIGH;      // ultimo estado ja confirmado
int leituraAnterior = HIGH;     // ultimo estado bruto lido
unsigned long mudouEm = 0;      // quando a leitura bruta mudou

void setup() {
  pinMode(PINO_BOTAO, INPUT_PULLUP);
  Serial.begin(9600);
}

void loop() {
  int leitura = digitalRead(PINO_BOTAO);

  if (leitura != leituraAnterior) {
    mudouEm = millis();
    leituraAnterior = leitura;
  }

  if ((millis() - mudouEm) > DEBOUNCE_MS && leitura != leituraEstavel) {
    leituraEstavel = leitura;

    // Dispara na descida (HIGH -> LOW), que e o instante do aperto.
    // Soltar nao gera nada.
    if (leituraEstavel == LOW) {
      Serial.println("interrogacao");
    }
  }
}
