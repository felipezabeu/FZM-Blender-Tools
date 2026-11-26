# FZM Builder 5.1.12: paredes conectadas e botão da porta

1. Abra uma cópia do projeto no Blender 5.1.x. Na vista 3D em **Object Mode**, de preferência de cima (Numpad 7), selecione uma parede criada no Builder. Deixe os gizmos da vista ligados.
2. Arraste uma das alças azuis para mover a ponta ou a alça verde do meio para mover a parede inteira. As paredes ligadas às pontas acompanham a mudança. Também dá para clicar na alça e depois clicar no destino.
3. **Ctrl** encaixa o deslocamento na grade; **Ctrl+Shift** usa a grade fina. **Esc** cancela. **Ctrl+Z** desfaz a operação toda. Pelo botão direito, **Wall Commands** também dá acesso a **Move Wall Start**, **Move Wall End** e **Move Entire Wall**; nesse caso clique num ponto de referência e depois no destino.

A ferramenta usa as conexões salvas pelo Builder, inclusive a junta de fechamento de um quarto. Ela não une paredes apenas sobrepostas nem converte encostes no meio da face em juntas. Portas e janelas continuam no mesmo lugar **em relação ao início da parede que as hospeda**. A ferramenta recusa encurtar uma parede por cima do seu próprio recorte de porta ou janela.

Pisos, divisores, pintura por ambiente, rodapés e revestimento do box que já existem não são refeitos automaticamente. Quando mudar o contorno, revise esses itens na cópia e recrie/reaplique o que precisar. Não substitua uma laje que contém recortes ou divisores sem verificar o resultado.

O botão **Open/Close** da porta é desenhado em tamanho de tela. Ele fica perto do vão, não aumenta com zoom ou rotação da vista e some quando o ponto de referência está fora da região visível. **Door Commands** continua disponível como alternativa.

### Validação
Para a base da edição, use `scripts/smoke_visual_wall_edit.py` no Blender 5.1.2, além das suítes de Floor Divider, Baseboards, Shower Wall Divider, Window Content e Door Pose. O par `scripts/probe_visual_wall_gui*.py` verifica arraste de canto/parede, undo e clique no botão com eventos gráficos reais.
