// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

/// @notice Closed ten-participant resource economy. No admin withdrawal or mint.
/// Resources have utility only inside this experiment; ETH payments go to sellers.
contract FlyGarden {
    uint256 public constant MAX_PRICE = 0.00001 ether;
    uint256 public constant HARVEST_DELAY = 120; // seconds, not an ETH reward
    mapping(address => uint8) public member; // 1..10, zero means not a participant
    mapping(address => mapping(uint8 => uint256)) public resourceBalance;
    mapping(address => uint256) public ask;
    mapping(address => uint256) public lastHarvest;
    address[10] public flies;
    bool private locked;
    event Trade(address indexed buyer, address indexed seller, uint8 resource, uint256 price);
    event Produced(address indexed fly, uint8 resource, uint256 output);
    event Harvested(address indexed fly, uint8 resource);
    event AskChanged(address indexed fly, uint256 price);
    error NotMember(); error Invalid(); error Unavailable(); error PaymentFailed();

    modifier participant() { if (member[msg.sender] == 0) revert NotMember(); _; }
    modifier nonReentrant() { if (locked) revert Invalid(); locked = true; _; locked = false; }

    constructor(address[10] memory participants) {
        for (uint8 i; i < 10; i++) {
            address fly = participants[i];
            if (fly == address(0) || member[fly] != 0) revert Invalid();
            member[fly] = i + 1;
            flies[i] = fly;
            uint8 kind = i % 2;
            resourceBalance[fly][kind] = 5;
            resourceBalance[fly][1-kind] = 2;
            ask[fly] = 0.000001 ether;
        }
    }

    function setAsk(uint256 price) external participant {
        if (price > MAX_PRICE) revert Invalid(); // zero pauses selling
        ask[msg.sender] = price;
        emit AskChanged(msg.sender, price);
    }

    function buy(address seller, uint256 maxPrice) external payable participant nonReentrant {
        if (seller == msg.sender || member[seller] == 0) revert Invalid();
        uint8 kind = (member[seller]-1) % 2;
        if ((member[msg.sender]-1) % 2 == kind) revert Invalid();
        uint256 price = ask[seller];
        if (price == 0 || price > maxPrice || msg.value != price || resourceBalance[seller][kind] == 0) revert Unavailable();
        resourceBalance[seller][kind]--;
        resourceBalance[msg.sender][kind]++;
        (bool paid,) = seller.call{value: price}("");
        if (!paid) revert PaymentFailed();
        emit Trade(msg.sender, seller, kind, price);
    }

    function produce() external participant {
        uint8 kind = (member[msg.sender]-1) % 2;
        if (resourceBalance[msg.sender][1-kind] == 0) revert Unavailable();
        resourceBalance[msg.sender][1-kind]--;
        resourceBalance[msg.sender][kind] += 2;
        emit Produced(msg.sender, kind, 2);
    }

    function harvest() external participant {
        if (block.timestamp < lastHarvest[msg.sender]+HARVEST_DELAY) revert Unavailable();
        lastHarvest[msg.sender] = block.timestamp;
        uint8 kind = (member[msg.sender]-1) % 2;
        resourceBalance[msg.sender][kind]++;
        emit Harvested(msg.sender, kind);
    }
}
