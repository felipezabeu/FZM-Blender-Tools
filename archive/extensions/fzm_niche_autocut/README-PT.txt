FZM Niche AutoCut 1.0.1 | recorte contínuo, não destrutivo
Blender 4.3–5.1. ZIP único, sem dependências externas.

1. Blender: Edit → Preferences → Get Extensions → Refresh Remote e atualize
   FZM Niche AutoCut. Se preferir ZIP: menu ▼ → Install from Disk.
2. Para uma nova inserção: File → Append → 29_Shower_Niche_Parametrico.blend →
   Collection → Shower Niche, com Instance Collections desligado.
   Se já arrastou o nicho e ficou só com uma instância (Empty), selecione-a e
   use N → FZM Niche → Tornar editável e ligar recorte. A opção Só tornar
   nicho editável prepara a peça sem iniciar cortes. A posição e o tamanho
   aparentes são mantidos; o objeto com os modificadores fica selecionado.
   Se o objeto editável estiver sem cortador, use Buscar o cortador no arquivo
   do nicho e selecione o 29_Shower_Niche_Parametrico.blend da mesma versão.
   Para mover o conjunto, selecione o objeto Shower Niche, não o cortador.
3. Em Object Mode, selecione Shower Niche. Na viewport: N → FZM Niche →
   Ligar recorte automático. Ele fica desligado por padrão em cada nicho novo.
4. Posicione o nicho e ajuste as dimensões nos Modifiers. Para funcionar, o volume
   do cortador precisa entrar no revestimento e na parede. O corte acompanha
   posição, rotação e dimensões. Quando o cortador sai da malha, o corte é removido.
   Durante edição em Object Mode, o complemento atualiza com um pequeno intervalo.
5. Para deixar um objeto intacto, selecione-o e clique Proteger esta malha na mesma aba.
   Permitir cortes nesta malha desfaz essa proteção. Atualizar cortes força nova busca.
   Para tirar os cortes do nicho, selecione-o e clique Desligar recorte automático.

O complemento procura malhas sólidas, locais, editáveis e visíveis no View Layer
atual. Não corta câmeras, luzes, instâncias não realizadas, referências Link
somente leitura, superfícies abertas ou peças de outros nichos. Malhas muito densas
ou problemáticas podem exigir ajuste manual. Para não mexer numa malha
compartilhada entre cenas, faça uma cópia local dela primeiro. O recurso está
pensado para posicionamento em Object Mode, não para simulação/animação/render
sem a extensão. Funciona com várias malhas (ex.: revestimento + parede).
Não aplica os modificadores e nunca apaga a geometria original.
Se outro objeto sólido entrar no volume, ele também pode ser cortado.

A extensão não é necessária para um corte manual. Em cada alvo, adicione um
Boolean → Difference → Exact e selecione Nicho • Boolean Cutter como Object.
Para o Shower Area com paredes, use a extensão. Ela recorta só os
revestimentos no grupo de Geometry Nodes do projeto antes da textura,
preserva piso/curbs e não altera o .blend da biblioteca. Um Boolean comum
depois desse grupo pode deformar a paginação perto da abertura.

Se desativar/desinstalar a extensão enquanto houver cortes, Booleans existentes
continuam nativos e guardam a última seleção de objetos. O recorte especial
dos revestimentos do Shower Area também mantém o grupo nativo ativo. Para limpar cortes
automáticos, desligue o recurso no nicho antes de desativar a extensão. Não
precisa de script embutido ou autoexecução do arquivo .blend.

Projeto visual: verifique modulação, travessas, passagem hidráulica e espessuras
no projeto real antes de executar a obra. Não é especificação construtiva.
