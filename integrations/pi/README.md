# Adapter Pi

O adapter Pi é distribuído dentro do pacote Python e instalado explicitamente com:

~~~fish
decisors integrate pi
~~~

Destino padrão:

~~~text
~/.pi/agent/extensions/decisors/index.js
~~~

Ele registra /decision e decision_evaluate, inicia decisors bridge como subprocesso persistente e conversa com o core via JSONL em stdin/stdout.

Toda lógica de provider permanece no Python. O adapter não chama Laya, TypeSafe ou OpenRouter diretamente.
