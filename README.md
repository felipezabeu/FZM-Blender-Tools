# FZM Blender Tools

Extensões internas da FZM Renovations para **Blender 5.1.2**. Este repositório contém código e as ferramentas de instalação; a geometria fica nos modelos mestre da biblioteca. Os modelos `.blend` e a biblioteca de assets ficam no **Google Drive**, em `Arquivos blender/Biblioteca_3D`.

## Extensões

| Extensão | Versão | Função |
|---|---:|---|
| FZM Vanity Controls | 1.2.1 | Paleta de gabinete (branco, cinza médio, azul marinho, carvalho claro); tops (quartz branco, branco com veios marcados, quartz escuro, concreto); hardware e splashes |
| FZM Builder | 5.1.28 | Paredes, pisos, portas, janelas e acabamentos de reforma; aba da vista 3D: `N > FZM Builder` |
| FZM Tile Panels | 1.0.0 | Painéis retangulares de tile com paginação, tamanhos e grout |

### FZM Builder 5.1.28

- **Door Casing** mantém a moldura tanto na cena 3D como na planta quando a porta faz parte das duas coleções. Para recuperar molduras que sumiram, reaplique o perfil usando **Door Casing → All Doors in This Scene** na cena 3D.

### FZM Builder 5.1.27

- Selecione a folha, a guarnição ou o arco de uma porta e clique com o botão direito. **Edit Door** e os atalhos compatíveis aparecem no primeiro menu, sem abrir um submenu. Os mesmos atalhos ficam em **N → FZM Builder → Room Layout → Doors & Windows → Door Commands**.
- **Flip Door Swing** e **Toggle Double Door** aparecem nas portas de abrir; **Flip Door Side**, quando há uma única folha. O botão azul continua só para abrir e fechar.

### FZM Builder 5.1.20

- O rodapé automático acompanha a ponta real da face da parede nos cantos em meia-esquadria, sem parar antes do encontro. Para corrigir rodapés existentes, reaplique **Add Baseboards → Automatic**.
- O snap das alças de parede usa as quatro arestas e os vértices reais, inclusive nas pontas em ângulo. **S** alterna o snap durante o arraste.
- **Update Floor Outline** leva o piso até a face interna mesmo sem porta. Reconhece cantos em contato físico e preserva o piso se o contorno continuar aberto.
- Uma caixa provisória de **Add Floor** pode ser recuperada ao fechar o contorno se houver um único perímetro identificável. Divisões manuais continuam protegidas.

### FZM Builder 5.1.18

- Para pôr rodapé em uma parede solta, selecione a parede e use **Add Baseboards → Selected Walls** ou o botão direito → **Add/Edit Wall Baseboards**. Não precisa selecionar o piso nem fechar o ambiente.
- Escolha **Side 1**, **Side 2** ou **Both Sides**. **Wrap Free Ends** cobre a espessura na ponta livre, sem avançar em uma parede conectada. O rodapé para na guarnição da porta e não passa pelo revestimento que chega até o piso.
- **Automatic** continua cuidando do perímetro do ambiente. Em um T, interrompe o rodapé onde a divisória entra no cômodo. O modo manual de perímetro fechado passou a se chamar **Selected Perimeter**.
- Os perfis **Colonial** e **Step Bevel** agora são diferentes para rodapé e guarnição. Nas duas guarnições, a borda fina fica voltada para o vão. Para atualizar uma peça já salva, reaplique **Add Baseboards** ou **Door Casing**; abrir o projeto não muda as peças existentes.
- Se for usar **Divide Wall** numa parede longa com rodapé aplicado diretamente, remova esse rodapé antes e reaplique nas duas partes depois de dividir.

### FZM Builder 5.1.16

- **Update Floor Outline** divide o piso entre áreas fechadas também quando a divisória encosta em outra parede. Continua sem sobrescrever um **Divide Floor** manual.
- **Room Layout → Walls → Divide Wall** divide a parede longa na junção em T entre duas paredes selecionadas. O corte é explícito e não acontece enquanto se desenha. Guarde paredes de projeto em cópia antes de testar. O comando recusa cortes através de vãos e paredes com revestimentos ou anexos que não podem ser transferidos com segurança.
- Ao arrastar a alça central de uma parede, trave em **X** ou **Y**, aponte para o lado desejado, digite só a distância na unidade do projeto e confirme com **Enter**. **Esc** cancela.
- **Wall Tiles** é o novo nome da **Shower Area**. Novos revestimentos têm espessura ajustável, inicialmente 1/2″. Revestimentos antigos mantêm a espessura anterior até que você altere o campo Lining Thickness.
- Rodapés existentes interrompem só no trecho em que o revestimento chega ao piso, respeitando **Wall Divider**, guarnições e a face oposta.

### FZM Builder 5.1.15

- **Floor Finish → Catalog** e **Shower Area → Tile Finish** têm seis acabamentos procedurais: branco com veios cinza, cinza, branco com veios bege, terrazzo claro, branco e cinza escuro. O catálogo não inclui fotos ou materiais oficiais da Besso.
- **Floor Tile Layout → Tile Shape** e **Shower Area → Tile Shape** separam formato e acabamento. Além do retangular há quadrado, hexagonal e penny round, com tamanho e juntas ajustáveis.
- O piso aceita uma foto local em **Floor Finish → Local Image**. Na parede do box, escolha **Custom Color or Photo → Tile-Face Photo** para importar a face de uma peça. As imagens importadas são incorporadas ao salvar o projeto.
- Nos pisos de madeira do catálogo, **Floor Finish → Board Angle** gira só o acabamento (0° por padrão). **Herringbone** alterna a paginação de tábuas corridas para espinha de peixe. Com **Floor Tile Layout** ativo, selecione **No Tile Layout** lá para mostrar as juntas da madeira.

### FZM Builder 5.1.14

- **Update Floor Outline** recorta o piso original ao encontrar um perímetro interno fechado e cria um piso separado para cada ambiente. Acabamento, paginação e **Paint Room Walls** funcionam por piso. Rodapés existentes são recalculados com os cortes de portas e molduras.
- No vão, os pisos encontram-se no centro da folha fechada ou, em um **Open**, no meio da parede. O arco 2D de portas de abrir segue a folha de verdade, fica acima do piso e mantém as anotações na vista de planta.
- O arraste de paredes encaixa em cantos, arestas e no esquadro dos vizinhos conectados. No arraste, **S** alterna o snap em paredes, **Q** alterna o esquadro, **X/Y** trava no eixo e **Ctrl** encaixa na grade. O snap não cria conexões novas sozinho.
- A barra **T** da vista 3D, em modo Objeto, tem atalhos para parede interna, porta de abrir e janela 3D. Selecione a ferramenta e depois clique na vista; os demais controles continuam no painel **N**.
- Inclui os estilos de porta da versão de teste 5.1.13 e usa **FZM Builder** também no menu superior.

### Alterações da vanity 1.2
- Cinza atualizado para `#777B80`, um pouco mais claro do que a proposta anterior `#62666B`.
- Azul atualizado para `#344760`, já aprovado.
- Adicionado **Carvalho Claro**, visual procedural inspirado na referência enviada (não textura oficial do fornecedor).
- Removido **Carrara** do menu. **Calacatta** substituído por *Branco veios marcados*, procedural com veios cinza mais fortes, inspirado na foto de referência.
- Materiais usam prefixo `FZM_Vanity_12_*` para não reutilizar automaticamente materiais antigos de 1.1.

## Geometria da vanity

A divisória interna deve ser removida do **arquivo-mestre** `FZM_Vanity_Master_30_v1.blend` (e do GLB-fonte), não por um botão do add-on. O add-on serve somente para materiais, acabamentos e splashes. Modelos já arrastados ao projeto não se atualizam automaticamente quando o mestre muda.

## Instalação manual para teste

No Blender, `Edit > Preferences > Get Extensions > menu > Install from Disk`, escolha o ZIP da extensão. Após ativação, a aba `N > FZM Vanity` ou `N > FZM Tile` aparecerá. A extensão da Vanity precisa encontrar uma vanity v1 com controlador `Vanity_30_Controller` e **importada como Append (não Collection Instance)**.

**Não atualize diretamente o `.blend` mestre sem testar em uma cópia.** Use `Aplicar acabamentos` para testar a cor e salve o arquivo de projeto.

## Publicação e atualizações remotas

O workflow em `.github/workflows/pages.yml` constrói os pacotes com Blender 5.1.2, gera o `index.json` oficial de repositório de extensões e publica como GitHub Pages **após configurar Pages com fonte GitHub Actions**, num repositório acessível ao Blender (público sem autenticação).

No Blender: `Edit > Preferences > Get Extensions > Repositories > + > Add Remote Repository`, usando `https://felipezabeu.github.io/FZM-Blender-Tools/index.json`. A nova versão será detectada após sincronização e exigirá confirmação para instalar.

Para migrar uma instalação anterior feita por ZIP, salve uma cópia do projeto e deixe o Home Builder original desativado. Desative a cópia local do FZM Builder antes de habilitar a versão do repositório remoto. Mantenha somente uma instância ativa; a integração ainda utiliza os mesmos IDs dos operadores do Home Builder original. Depois da configuração inicial, use a sincronização e a atualização de extensões do próprio Blender.

## Pintura de portas, molduras e rodapés no FZM Builder

- **N → FZM Builder → Room Layout → Doors & Windows → Door Paint:** selecione uma porta 3D ou uma parte dela. Marque **Paint Door Leaf** para mudar a folha sem alterar ferragens, vidro ou espelho. Em **Casing Color**, escolha **Keep Existing**, **Same as Door** ou **Different Color**. Dá para mudar só a moldura deixando **Paint Door Leaf** desmarcado.
- **N → FZM Builder → Room Layout → Floor & Ceiling → Baseboard Paint:** selecione o rodapé, o piso do cômodo ou, para rodapés anexados diretamente à parede, a própria parede.
- Os dois comandos aceitam **HEX**, **RGB** ou **Palette**. Use **Selection** ou **All in Scene**; **Use Default White** restaura o branco. Peças novas continuam brancas por padrão. Para ver o resultado, use **Material Preview**.

## Tetos e iluminação no FZM Builder 5.1.26

- Em **Room Layout → Floor & Ceiling → Add Ceiling**, o Builder cria um teto por ambiente fechado. Para dividir um teto antigo depois de adicionar paredes, selecione-o e clique em **Update Ceiling Outline**. A atualização mantém a altura e o acabamento existentes.
- Selecione o teto do ambiente e, em **Lighting → Add Room Lights**, escolha **4″ Recessed Pot Light** ou **Custom Point** e ajuste a temperatura. Para editar ou converter uma luminária, selecione a luz ou o aro e use **Update Room Lights**.
- O preset começa em 3000 K e 12 W de render no Blender. Isso não é potência elétrica nem conversão de lúmens; o [HALO LTC 4″ de 650 lm](https://www.cooperlighting.com/api/assets/v1/file/CLS/content/halo-ltc4-lt-dm-5cct-specsheet/HALO-4-inch-LT-Canless-LED-Downlight-spec-sheet.pdf) é só uma referência de produto. Potência e suavidade ficam em **Advanced**. O aro e a lente viajam como malha na exportação glTF/GLB; o cone de luz só é reproduzido se o visualizador carregar as luzes do glTF.

## FZM Niche AutoCut 1.0.1

No repositório remoto acima, abra **Get Extensions**, atualize a lista (**Sync**) e instale **FZM Niche AutoCut**. Não é necessário baixar um ZIP. Se já instalou uma cópia de teste por ZIP, desative a cópia local para não ativar a extensão duas vezes.

Em **Object Mode**, faça **Append → Collection → Shower Niche** de `29_Shower_Niche_Parametrico.blend`. Selecione o objeto **Shower Niche** e use **N → FZM Niche → Ligar recorte automático**. O recurso começa desligado para cada nicho. Recorta as malhas sólidas, locais, editáveis e visíveis no View Layer atual, sem aplicar o corte. A seleção de alvos acompanha o nicho. Para preservar um objeto específico, selecione-o e use **Proteger esta malha**.

Se a peça já inserida é uma instância sem modificadores, selecione-a e use **N → FZM Niche → Tornar editável e ligar recorte**. Ela conserva a posição, ganha um cortador independente e fica selecionada. Se faltar só o cortador, **Buscar o cortador no arquivo do nicho** recupera a peça correspondente sem mover o nicho.

O **Shower Area** aplica o recorte aos revestimentos antes dos acabamentos, preservando a paginação e o piso. O arquivo do asset não está incluído no pacote da extensão. Veja [o guia do AutoCut](extensions/fzm_niche_autocut/README-PT.txt) para limites e uso manual.

## Limites

- Não são acabamentos nem modelos oficiais da Topcan/Besso. Verificar licenças e medidas para obras.
- Shaders foram validados estaticamente, mas não testados em execução dentro do Blender 5.1.2.
- A ferramenta Tile Panels trabalha inicialmente com superfícies retangulares; não substitui paginação construtiva ou cálculo de desperdício.

## Licenças

FZM Vanity Controls e FZM Niche AutoCut: GPL-3.0-or-later. FZM Tile Panels: MIT (`LICENSE.txt` na extensão).
