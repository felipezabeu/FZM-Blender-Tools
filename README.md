# FZM Blender Tools

Extensões internas da FZM Renovations para **Blender 5.1.2**. Este repositório contém código e as ferramentas de instalação; a geometria fica nos modelos mestre da biblioteca. Os modelos `.blend` e a biblioteca de assets ficam no **Google Drive**, em `Arquivos blender/Biblioteca_3D`.

## Extensões

| Extensão | Versão | Função |
|---|---:|---|
| FZM Vanity Controls | 1.2.1 | Paleta de gabinete (branco, cinza médio, azul marinho, carvalho claro); tops (quartz branco, branco com veios marcados, quartz escuro, concreto); hardware e splashes |
| FZM Builder | 5.1.12 | Paredes, pisos, portas, janelas e acabamentos de reforma; aba da vista 3D: `N > FZM Builder` |
| FZM Tile Panels | 1.0.0 | Painéis retangulares de tile com paginação, tamanhos e grout |

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