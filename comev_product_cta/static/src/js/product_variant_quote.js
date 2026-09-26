/** @odoo-module **/

function updateQuoteLink() {
    const link = document.querySelector(".js-product-quote-link");
    const variantInput = document.querySelector("input[name='product_id']");
    if (!link || !variantInput || !variantInput.value) {
        return;
    }
    link.href = `${link.dataset.baseUrl}?product_variant_id=${encodeURIComponent(variantInput.value)}`;
}

document.addEventListener("DOMContentLoaded", () => {
    updateQuoteLink();
    const productDetails = document.querySelector("#product_details");
    if (!productDetails) {
        return;
    }
    productDetails.addEventListener("change", () => window.setTimeout(updateQuoteLink, 0));
    const variantInput = productDetails.querySelector("input[name='product_id']");
    if (variantInput) {
        new MutationObserver(updateQuoteLink).observe(variantInput, {
            attributes: true,
            attributeFilter: ["value"],
        });
    }
});
