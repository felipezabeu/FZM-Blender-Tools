# Abrir e fechar portas direto na vista 3D

- No modo Objeto, selecione a folha 3D da porta ou o seu vão. O botão aparece próximo à parte superior do vão, sem mover a porta só por selecioná-la. ▶ abre; a seta de retorno fecha. Passe o mouse para ver a função. O botão fica na referência do vão mesmo com a folha aberta ou dentro da parede.
- O menu de contexto da porta também mostra **Open Door** ou **Close Door** conforme a pose atual. Use-o quando os gizmos estiverem desligados ou o botão estiver fora da área visível.
- Funciona com **Single**, **Double**, **Sliding Closet (Bypass)**, **Bifold** e **Pocket**. Para uma Single/Double sem folha 3D, ative antes **Edit Door → Show 3D Leaf**. **Open** (vão vazio) não recebe o comando.
- O comando usa o **Open Amount** já existente, sem modificar o recorte de parede, dimensões, lado de giro ou estilo. Ao fechar uma porta parcialmente aberta pelo botão, a pose atual é lembrada para o próximo clique. Sem pose lembrada ela abre até o limite visual do modelo. O controle continua disponível em **Edit Door**.
- Referência: Home Builder 3 documentou **Open Door** nas propriedades de porta; Home Builder 5 documenta o acesso por menu de contexto aos vãos, sem prometer a folha 3D. Este botão contextual é do FZM Builder.

## Um diálogo para qualquer porta
- Selecione uma porta ou seu vão e escolha **Door Commands → Edit Door** no botão direito, ou **Edit Door** na barra lateral **Doors & Windows**. O mesmo diálogo mostra as medidas, o deslocamento, o estilo e a pose que se aplicam à porta selecionada. Nas portas de giro ele reúne o sentido de abertura, a mão (Single) e a opção de ativar ou ocultar a folha 3D. **Open** mostra só as medidas e o deslocamento.
- **Door Casing** fica ao lado de **Edit Door**. Continua separado porque pode aplicar guarnição a várias portas de uma vez. O botão rápido de abrir/fechar continua disponível.

Testes: `scripts/smoke_unified_door_edit.py` cobre os caminhos do menu e da barra lateral, campos por tipo, validação e recarregamento. `scripts/smoke_viewport_door_pose.py` verifica a seleção passiva, posição da interface, vinculação do botão/operador e menu, regeneração visual, isolamento por porta e reabertura do arquivo. O teste headless usa um registrador para as chamadas da camada gráfica; o clique físico/GPU e a interface Windows ainda requerem validação interativa.
