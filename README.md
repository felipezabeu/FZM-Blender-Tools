# FZM Blender Tools

Extensões internas da FZM Renovations para **Blender 5.1.2**. Este repositório contém código e as ferramentas de instalação; a geometria fica nos modelos mestre da biblioteca. Os modelos `.blend` e a biblioteca de assets ficam no **Google Drive**, em `Arquivos blender/Biblioteca_3D`.

## Extensões

| Extensão | Versão | Função |
|---|---:|---|
| FZM Vanity Controls | 1.2.1 | Paleta de gabinete (branco, cinza médio, azul marinho, carvalho claro); tops (quartz branco, branco com veios marcados, quartz escuro, concreto); hardware e splashes |
| FZM Builder | 5.1.16 | Paredes, pisos, portas, janelas e acabamentos de reforma; aba da vista 3D: `N > FZM Builder` |
| FZM Tile Panels | 1.0.0 | Painéis retangulares de tile com paginação, tamanhos e grout |

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

## Limites

- Não são acabamentos nem modelos oficiais da Topcan/Besso. Verificar licenças e medidas para obras.
- Shaders foram validados estaticamente, mas não testados em execução dentro do Blender 5.1.2.
- A ferramenta Tile Panels trabalha inicialmente com superfícies retangulares; não substitui paginação construtiva ou cálculo de desperdício.

## Licenças

FZM Vanity Controls: GPL-3.0-or-later. FZM Tile Panels: MIT (`LICENSE.txt` na extensão).