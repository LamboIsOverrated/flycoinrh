// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

interface IQuoteToken {
    function approve(address spender, uint256 value) external returns (bool);
}
interface IQuoteRouter {
    struct Params {
        address tokenIn; address tokenOut; uint24 fee; address recipient;
        uint256 amountIn; uint256 amountOutMinimum; uint160 sqrtPriceLimitX96;
    }
    function exactInputSingle(Params calldata params) external payable returns (uint256);
}
interface IQuotePool {
    function swap(address recipient, bool zeroForOne, int256 amountSpecified, uint160 limit, bytes calldata data)
        external returns (int256, int256);
}
/// Used ONLY as transient eth_call code through a state override. Never deployed.
contract QuoteProbe {
    address private expectedPool;
    function quoteSell(address pool, uint256 units) external returns (uint256 output) {
        require(units > 0 && units < uint256(type(int256).max), "amount");
        expectedPool = pool;
        // PONS is token1; its sale receives token0 (WETH).
        try IQuotePool(pool).swap(address(this), false, int256(units),
            1461446703485210103287273052203988822378723970341, "") returns (int256, int256) {
            revert("unexpected success");
        } catch (bytes memory reason) {
            require(reason.length == 32, "pool quote failed");
            output = abi.decode(reason, (uint256));
        }
    }
    function uniswapV3SwapCallback(int256 amount0, int256 amount1, bytes calldata) external view {
        require(msg.sender == expectedPool && amount0 < 0 && amount1 > 0, "callback");
        uint256 result = uint256(-amount0);
        assembly { mstore(0, result) revert(0, 32) }
    }
    function roundTrip(address router, address weth, address token, uint24 fee, uint256 amount)
        external returns (uint256 bought, uint256 returnedWeth)
    {
        bought = IQuoteRouter(router).exactInputSingle{value: amount}(
            IQuoteRouter.Params(weth, token, fee, address(this), amount, 1, 0));
        require(IQuoteToken(token).approve(router, bought), "approve");
        returnedWeth = IQuoteRouter(router).exactInputSingle(
            IQuoteRouter.Params(token, weth, fee, address(this), bought, 1, 0));
    }
}
