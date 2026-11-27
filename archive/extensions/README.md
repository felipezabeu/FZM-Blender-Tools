# Ferramentas FZM arquivadas

Estas duas extensões estão preservadas para manutenção de projetos antigos. Não fazem parte da publicação do GitHub Pages nem aparecem em **Get Extensions**.

| Ferramenta | Última versão | Quando ainda pode ser útil |
|---|---|---|
| [FZM Niche AutoCut](fzm_niche_autocut/) | 1.0.1 | Atualizar recortes automáticos de um nicho avulso em malhas externas ao Shower Area. |
| [FZM Vanity Controls](fzm_vanity_controls/) | 1.2.1 | Mudar acabamentos de uma antiga Vanity Master 30 com controlador `Vanity_30_Controller`. |

Para projetos atuais, use os próprios **Modifiers** do Shower Area e das vanities da biblioteca; o nicho integrado recorta apenas as paredes do próprio asset. Desinstalar a AutoCut não remove os cortes já salvos, mas eles deixam de procurar novos alvos automaticamente.

Se precisar restaurar uma ferramenta legada, baixe o código e gere o ZIP da pasta correspondente com `blender --command extension build --source-dir <pasta> --output-dir <destino>`, depois use **Install from Disk**. As instruções de atualização remota nos guias antigos são históricas.

### Alterações da vanity 1.2
- Cinza atualizado para `#777B80`, um pouco mais claro do que a proposta anterior `#62666B`.
- Azul atualizado para `#344760`, já aprovado.
- Adicionado **Carvalho Claro**, visual procedural inspirado na referência enviada (não textura oficial do fornecedor).
- Removido **Carrara** do menu. **Calacatta** substituído por *Branco veios marcados*, procedural com veios cinza mais fortes, inspirado na foto de referência.
- Materiais usam prefixo `FZM_Vanity_12_*` para não reutilizar automaticamente materiais antigos de 1.1.

## Geometria da vanity

A divisória interna deve ser removida do **arquivo-mestre** `FZM_Vanity_Master_30_v1.blend` (e do GLB-fonte), não por um botão do add-on. O add-on serve somente para materiais, acabamentos e splashes. Modelos já arrastados ao projeto não se atualizam automaticamente quando o mestre muda.
